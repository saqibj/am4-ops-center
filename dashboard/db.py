"""SQLite access helpers (sync) for the dashboard."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser
from fastapi import Request

DB_PATH = os.environ.get("AM4_ROUTEMINE_DB", "am4_data.db")


def get_db() -> sqlite3.Connection:
    p = Path(DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    from database.extraction_runs import ensure_extraction_runs_schema
    from database.schema import ensure_route_aircraft_baseline_prices

    ensure_route_aircraft_baseline_prices(conn)
    ensure_extraction_runs_schema(conn)
    return conn


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    cur = conn.execute(sql, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> dict | None:
    cur = conn.execute(sql, tuple(params))
    row = cur.fetchone()
    return dict(row) if row else None


def db_file_size_bytes() -> int | None:
    p = Path(DB_PATH)
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


_HUB_FRESHNESS_SQL = """
    SELECT UPPER(TRIM(a.iata)) AS hub, MAX(ra.extracted_at) AS latest
    FROM route_aircraft ra
    JOIN airports a ON ra.origin_id = a.id
    WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
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


def hub_freshness_context(request: Request) -> dict[str, Any]:
    """Per-origin IATA: age of newest extracted route row (valid routes only)."""
    try:
        conn = get_db()
        try:
            rows = fetch_all(conn, _HUB_FRESHNESS_SQL)
        finally:
            conn.close()
    except FileNotFoundError:
        return {
            "hub_freshness_by_iata": {},
            "hub_freshness_list": [],
            "stale_hub_banner": None,
        }
    return _hub_freshness_from_rows(request, rows)


def base_context(request: Request) -> dict:
    empty_fresh = {
        "hub_freshness_by_iata": {},
        "hub_freshness_list": [],
        "stale_hub_banner": None,
    }
    try:
        conn = get_db()
        try:
            row = fetch_one(
                conn,
                "SELECT COUNT(*) AS route_count FROM route_aircraft WHERE is_valid = 1",
            )
            rc = int(row["route_count"]) if row else 0
            frows = fetch_all(conn, _HUB_FRESHNESS_SQL)
            fresh = _hub_freshness_from_rows(request, frows)
        finally:
            conn.close()
    except FileNotFoundError:
        rc = 0
        fresh = empty_fresh
    return {
        "request": request,
        "db_name": os.path.basename(DB_PATH),
        "route_count": rc,
        **fresh,
    }
