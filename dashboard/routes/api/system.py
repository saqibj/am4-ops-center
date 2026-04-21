"""System status JSON + HTMX fragment for sidebar footer."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.services.hubs import SQL_EXPLORER_HUB_IATAS
from dashboard.db import fetch_all, fetch_one, get_read_db
from dashboard.server import templates
from database.extraction_runs import list_completed_runs
from dashboard.routes.api.shared import _EXTRACTION_LOCK

router = APIRouter()


def _parse_dt(val: object) -> datetime | None:
    if val is None:
        return None
    try:
        dt = date_parser.parse(str(val).strip())
    except (ValueError, TypeError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _total_db_rows(conn: sqlite3.Connection) -> int:
    """Consolidated count of major tables instead of scanning all tables."""
    try:
        row = conn.execute("""
            SELECT SUM(cnt) FROM (
                SELECT COUNT(*) AS cnt FROM route_aircraft
                UNION ALL SELECT COUNT(*) FROM my_routes
                UNION ALL SELECT COUNT(*) FROM my_fleet
                UNION ALL SELECT COUNT(*) FROM airports
                UNION ALL SELECT COUNT(*) FROM aircraft
            )
        """).fetchone()
        return int(row[0]) if row and row[0] else 0
    except sqlite3.OperationalError:
        return 0


def _latest_extraction_iso_by_hub(conn: sqlite3.Connection) -> dict[str, str]:
    """Map hub IATA -> latest finished_at ISO from completed runs (hubs CSV)."""
    # Reduce limit to 100 as that is plenty to find the latest for all hubs.
    runs = list_completed_runs(conn, limit=100)
    hub_to_dt: dict[str, datetime] = {}
    for run in runs:
        dt = _parse_dt(run.get("finished_at"))
        if dt is None:
            continue
        hubs_csv = (run.get("hubs") or "").strip()
        for part in re.split(r"[\s,;]+", hubs_csv):
            hub = part.strip().upper()
            if not hub:
                continue
            prev = hub_to_dt.get(hub)
            if prev is None or dt > prev:
                hub_to_dt[hub] = dt
    return {k: v.isoformat() for k, v in hub_to_dt.items()}


def _workers_state(conn: sqlite3.Connection | None) -> str:
    if _EXTRACTION_LOCK.locked():
        return "running"
    if conn is not None:
        try:
            row = fetch_one(
                conn,
                "SELECT COUNT(*) AS c FROM extraction_runs WHERE finished_at IS NULL",
            )
            if row and int(row.get("c") or 0) > 0:
                return "running"
        except sqlite3.OperationalError:
            pass
    return "idle"


def _relative_short(now: datetime, dt: datetime | None) -> str:
    if dt is None:
        return "—"
    delta = now - dt
    secs = max(0, int(delta.total_seconds()))
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 48:
        return f"{hrs}h ago"
    days = hrs // 24
    return f"{days}d ago"


def _bar_tier_minutes(minutes: float | None) -> str:
    if minutes is None:
        return "unknown"
    if minutes < 30:
        return "fresh"
    if minutes <= 120:
        return "warn"
    return "stale"


def build_system_status_payload(conn: sqlite3.Connection | None) -> dict:
    """Context for JSON + sidebar_status partial."""
    now = datetime.now(timezone.utc)
    extraction: dict[str, str] = {}
    db_rows = 0
    hub_bars: list[dict[str, object]] = []
    workers = "idle"

    if conn is not None:
        try:
            # Optimization: batch these or at least simplify.
            # _total_db_rows is now 1 query. _workers_state is 1 query.
            # extraction is 1 query. hub_rows is 1 query.
            # Total ~4 queries instead of 29+.
            workers = _workers_state(conn)
            db_rows = _total_db_rows(conn)
            extraction = _latest_extraction_iso_by_hub(conn)
            hub_rows = fetch_all(conn, SQL_EXPLORER_HUB_IATAS)
        except sqlite3.OperationalError:
            hub_rows = []
            extraction = {}
            db_rows = 0
    else:
        hub_rows = []

    latest_any: datetime | None = None
    for iso in extraction.values():
        dt = _parse_dt(iso)
        if dt and (latest_any is None or dt > latest_any):
            latest_any = dt

    for row in hub_rows:
        iata = str(row.get("iata") or "").strip().upper()
        if not iata:
            continue
        iso = extraction.get(iata)
        dt = _parse_dt(iso) if iso else None
        minutes = (
            (now - dt).total_seconds() / 60.0 if dt is not None else None
        )
        tier = _bar_tier_minutes(minutes)
        hub_bars.append(
            {
                "iata": iata,
                "tier": tier,
                "minutes": minutes,
            }
        )

    extraction_relative = _relative_short(now, latest_any)

    return {
        "extraction": extraction,
        "db_rows": db_rows,
        "workers": workers,
        "hub_bars": hub_bars,
        "extraction_relative": extraction_relative,
    }


@router.get("/system/status")
def api_system_status(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
):
    payload = build_system_status_payload(conn)
    if request.headers.get("hx-request"):
        return templates.TemplateResponse(
            request,
            "_partials/sidebar_status.html",
            {"sys_status": payload},
        )
    return JSONResponse(
        {
            "extraction": payload["extraction"],
            "db_rows": payload["db_rows"],
            "workers": payload["workers"],
        }
    )
