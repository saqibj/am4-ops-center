"""SQLite access helpers (sync) for the dashboard."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.env_compat import resolved_env_db
from app.paths import db_path
from database.settings_dao import read_game_mode
from dateutil import parser as date_parser
from fastapi import Request

# Highest numbered SQL migration under ``dashboard/db/migrations/``; bump when schema changes.
SCHEMA_VERSION = 4

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
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")


def run_sql_migrations(conn: sqlite3.Connection) -> None:
    """Run SQL migrations in dashboard/db/migrations once per DB."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    migrations_dir = Path(__file__).resolve().parent / "db" / "migrations"
    if not migrations_dir.exists():
        return

    migrations_applied = 0
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        row = conn.execute("SELECT 1 FROM _migrations WHERE filename = ?", (migration_file.name,)).fetchone()
        if not row:
            conn.executescript(migration_file.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (migration_file.name,))
            migrations_applied += 1

    if migrations_applied > 0:
        conn.execute("ANALYZE")
        conn.commit()


def get_read_conn() -> sqlite3.Connection:
    p = current_db_path()
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    from dashboard.middleware.profiling import instrument_connection

    return instrument_connection(conn)


_WRITE_CONN_RAW: sqlite3.Connection | None = None
_WRITE_CONN_PATH: str | None = None
_WRITE_CONN_GUARD = threading.Lock()
_WRITE_INIT_GUARD = threading.Lock()


class _WriteConnectionLease:
    """Connection lease that releases global writer lock on close()."""

    __slots__ = ("_conn", "_lock", "_closed")

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock):
        self._conn = conn
        self._lock = lock
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._lock.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _ensure_write_conn() -> sqlite3.Connection:
    global _WRITE_CONN_RAW, _WRITE_CONN_PATH
    p = current_db_path()
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")
    want = str(p.resolve())
    with _WRITE_INIT_GUARD:
        if _WRITE_CONN_RAW is not None and _WRITE_CONN_PATH != want:
            try:
                _WRITE_CONN_RAW.close()
            except sqlite3.Error:
                pass
            _WRITE_CONN_RAW = None
            _WRITE_CONN_PATH = None
        if _WRITE_CONN_RAW is None:
            conn = sqlite3.connect(want, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _apply_pragmas(conn)
            _WRITE_CONN_RAW = conn
            _WRITE_CONN_PATH = want
    return _WRITE_CONN_RAW


def prepare_for_db_file_replacement() -> None:
    """Close the shared writer SQLite connection so the DB file can be replaced on disk.

    Blocks until no other thread holds an active write lease, then drops the cached
    connection. Intended for restore flows (single-user local app).
    """
    global _WRITE_CONN_RAW, _WRITE_CONN_PATH
    _WRITE_CONN_GUARD.acquire()
    try:
        with _WRITE_INIT_GUARD:
            if _WRITE_CONN_RAW is not None:
                try:
                    _WRITE_CONN_RAW.close()
                except sqlite3.Error:
                    pass
                _WRITE_CONN_RAW = None
                _WRITE_CONN_PATH = None
    finally:
        _WRITE_CONN_GUARD.release()


def get_write_conn():
    """Return serialized lease over shared writer connection."""
    _WRITE_CONN_GUARD.acquire()
    try:
        conn = _ensure_write_conn()
    except Exception:
        _WRITE_CONN_GUARD.release()
        raise
    from dashboard.middleware.profiling import instrument_connection

    return instrument_connection(_WriteConnectionLease(conn, _WRITE_CONN_GUARD))


def get_db():
    """Deprecated shared accessor; mapped to serialized writer connection."""
    return get_write_conn()


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
    try:
        return get_read_conn(), True
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


# Hub list comes from v_my_hubs (my_hubs + airports), not from DISTINCT origin_id in
# route_aircraft — otherwise orphan route rows kept a "ghost" hub in freshness UI.
# Per-origin_id MAX(extracted_at) is still grouped in a subquery; LEFT JOIN so hubs with
# no valid routes yet still appear (latest NULL). Outer GROUP BY hub IATA if multiple
# my_hubs rows ever shared one IATA.
_HUB_FRESHNESS_SQL = """
    SELECT UPPER(TRIM(v.iata)) AS hub, MAX(mx.latest) AS latest
    FROM v_my_hubs v
    LEFT JOIN (
        SELECT origin_id, MAX(extracted_at) AS latest
        FROM route_aircraft
        WHERE is_valid = 1
        GROUP BY origin_id
    ) AS mx ON mx.origin_id = v.airport_id
    WHERE v.iata IS NOT NULL AND TRIM(v.iata) != ''
    GROUP BY UPPER(TRIM(v.iata))
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
        c = get_read_conn()
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
