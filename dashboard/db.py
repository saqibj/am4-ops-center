"""SQLite access helpers (sync) for the dashboard."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.env_compat import resolved_env_db
from app.paths import db_path
from database.settings_dao import read_game_mode
from dateutil import parser as date_parser
from fastapi import Request

HTML_DB_NOT_FOUND = (
    "<p class='text-amber-400'>Database not found. Configure AM4_OPS_CENTER_DB "
    "(or legacy AM4_ROUTEMINE_DB) or run an extract.</p>"
)


def current_db_path() -> Path:
    env_db = resolved_env_db()
    if env_db:
        return Path(env_db).expanduser().resolve()
    db_path_override = globals().get("DB_PATH")
    if db_path_override:
        return Path(str(db_path_override)).expanduser().resolve()
    return db_path().resolve()


# Backward-compatibility for modules/tests that monkeypatch dashboard.db.DB_PATH.
DB_PATH = str(current_db_path())


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")


def get_db() -> sqlite3.Connection:
    p = current_db_path()
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    from dashboard.middleware.profiling import instrument_connection

    return instrument_connection(conn)


def _close_stale_read_if_path_changed(request: Request) -> None:
    """If DB env / DB_PATH was monkeypatched (tests), drop the old shared reader."""
    want = str(current_db_path())
    backed = getattr(request.app.state, "db_read_path", None)
    raw = getattr(request.app.state, "db_read", None)
    if raw is not None and backed is not None and backed != want:
        try:
            raw.close()
        except sqlite3.Error:
            pass
        request.app.state.db_read = None
        request.app.state.db_read_path = None


def open_read_connection(request: Request) -> tuple[sqlite3.Connection | None, bool]:
    """Return (instrumented connection, needs_close). Caller must close when needs_close is True."""
    _close_stale_read_if_path_changed(request)
    from dashboard.middleware.profiling import instrument_connection

    want = str(current_db_path())
    raw = getattr(request.app.state, "db_read", None)
    backed = getattr(request.app.state, "db_read_path", None)
    if raw is not None and backed == want:
        return instrument_connection(raw), False
    try:
        return get_db(), True
    except FileNotFoundError:
        return None, False


def get_read_db(request: Request):
    """FastAPI dependency: shared long-lived reader, or per-request connection when path differs."""
    conn, owns = open_read_connection(request)
    if conn is None:
        yield None
        return
    try:
        yield conn
    finally:
        if owns:
            conn.close()


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    cur = conn.execute(sql, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> dict | None:
    cur = conn.execute(sql, tuple(params))
    row = cur.fetchone()
    return dict(row) if row else None


def db_file_size_bytes() -> int | None:
    p = current_db_path()
    if not p.exists():
        return None
    return p.stat().st_size


def _parse_extracted_at(val: Any) -> datetime | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        dt = date_parser.parse(s)
    except (ValueError, TypeError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _freshness_days_utc(now: datetime, dt: datetime | None) -> int | None:
    if dt is None:
        return None
    delta = now - dt
    return max(0, int(delta.total_seconds() // 86400))


def _freshness_tier(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days <= 7:
        return "green"
    if days <= 14:
        return "yellow"
    return "red"


def _freshness_dot_class(tier: str) -> str:
    if tier == "green":
        return "bg-emerald-400"
    if tier == "yellow":
        return "bg-amber-400"
    if tier == "red":
        return "bg-rose-500"
    return "bg-slate-500"


# Per-origin_id MAX(extracted_at) uses index-friendly GROUP BY origin_id; outer GROUP BY
# hub IATA preserves semantics if multiple origin_ids ever shared one IATA code.
_HUB_FRESHNESS_SQL = """
    SELECT UPPER(TRIM(a.iata)) AS hub, MAX(mx.latest) AS latest
    FROM (
        SELECT origin_id, MAX(extracted_at) AS latest
        FROM route_aircraft
        WHERE is_valid = 1
        GROUP BY origin_id
    ) AS mx
    JOIN airports a ON mx.origin_id = a.id
    WHERE a.iata IS NOT NULL AND TRIM(a.iata) != ''
    GROUP BY UPPER(TRIM(a.iata))
"""


def _hub_freshness_from_rows(
    request: Request, rows: list[dict]
) -> dict[str, Any]:
    """Build hub_freshness_* keys from SQL rows (same connection as route count)."""
    now = datetime.now(timezone.utc)
    by_iata: dict[str, dict[str, Any]] = {}
    for r in rows:
        hub = str(r.get("hub") or "").strip().upper()
        if not hub:
            continue
        latest_raw = r.get("latest")
        dt = _parse_extracted_at(latest_raw)
        days = _freshness_days_utc(now, dt)
        tier = _freshness_tier(days)
        parts: list[str] = []
        if days is not None:
            parts.append(f"{days}d")
        if tier == "red":
            parts.append("stale")
        suffix = f" ({', '.join(parts)})" if parts else ""
        by_iata[hub] = {
            "days": days,
            "tier": tier,
            "latest": str(latest_raw) if latest_raw is not None else None,
            "option_suffix": suffix,
            "dot_class": _freshness_dot_class(tier),
        }

    hub_freshness_list = [
        {"iata": iata, **by_iata[iata]} for iata in sorted(by_iata.keys())
    ]

    stale_hub_banner: dict[str, Any] | None = None
    for param in ("hub", "origin"):
        raw = (request.query_params.get(param) or "").strip().upper()
        if not raw or raw not in by_iata:
            continue
        fi = by_iata[raw]
        if fi.get("tier") == "red" and fi.get("days") is not None:
            stale_hub_banner = {"hub": raw, "days": fi["days"], "param": param}
            break

    return {
        "hub_freshness_by_iata": by_iata,
        "hub_freshness_list": hub_freshness_list,
        "stale_hub_banner": stale_hub_banner,
    }


def hub_freshness_context(
    request: Request, conn: sqlite3.Connection | None
) -> dict[str, Any]:
    """Per-origin IATA: age of newest extracted route row (valid routes only)."""
    if conn is None:
        return {
            "hub_freshness_by_iata": {},
            "hub_freshness_list": [],
            "stale_hub_banner": None,
        }
    try:
        rows = fetch_all(conn, _HUB_FRESHNESS_SQL)
    except sqlite3.OperationalError:
        return {
            "hub_freshness_by_iata": {},
            "hub_freshness_list": [],
            "stale_hub_banner": None,
        }
    return _hub_freshness_from_rows(request, rows)


def _resolve_game_mode(conn: sqlite3.Connection | None) -> str:
    """Persisted game mode for nav/badge; ``easy`` if DB missing or unreadable."""
    if conn is not None:
        try:
            return read_game_mode(conn)
        except sqlite3.OperationalError:
            return "easy"
    try:
        c = get_db()
        try:
            return read_game_mode(c)
        finally:
            c.close()
    except (FileNotFoundError, sqlite3.OperationalError):
        return "easy"


def base_context(
    request: Request, conn: sqlite3.Connection | None
) -> dict:
    empty_fresh = {
        "hub_freshness_by_iata": {},
        "hub_freshness_list": [],
        "stale_hub_banner": None,
    }
    game_mode = _resolve_game_mode(conn)
    if conn is None:
        return {
            "request": request,
            "db_name": current_db_path().name,
            "route_count": 0,
            "game_mode": game_mode,
            **empty_fresh,
        }
    try:
        row = fetch_one(
            conn,
            "SELECT COUNT(*) AS route_count FROM route_aircraft WHERE is_valid = 1",
        )
        rc = int(row["route_count"]) if row else 0
        frows = fetch_all(conn, _HUB_FRESHNESS_SQL)
        fresh = _hub_freshness_from_rows(request, frows)
    except sqlite3.OperationalError:
        rc = 0
        fresh = empty_fresh
    return {
        "request": request,
        "db_name": current_db_path().name,
        "route_count": rc,
        "game_mode": game_mode,
        **fresh,
    }
