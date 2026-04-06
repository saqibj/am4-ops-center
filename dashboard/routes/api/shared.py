"""Shared helpers and extraction lock for /api/* route modules."""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from dashboard.db import fetch_all, fetch_one
from dashboard.hub_freshness import STALE_AFTER_DAYS


def _stale_cutoff_iso(days: int = STALE_AFTER_DAYS) -> str:
    """ISO timestamp for 'now minus N days' in UTC, for SQL bound parameters."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


_EXTRACTION_LOCK = threading.Lock()

_EXTRACTION_BUSY_MSG = (
    "Another extraction is already in progress. Wait for it to finish."
)


def _try_acquire_extraction_lock() -> bool:
    """Return True if the lock was acquired (non-blocking). False if an extraction is already running."""
    return _EXTRACTION_LOCK.acquire(blocking=False)


def _release_extraction_lock() -> None:
    try:
        _EXTRACTION_LOCK.release()
    except RuntimeError:
        pass


HUB_SORT_COLUMNS = {
    "profit_per_ac_day",
    "profit_per_trip",
    "contribution",
    "income_per_ac_day",
    "destination",
    "aircraft",
    "distance_km",
    "flight_time_hrs",
    "trips_per_day",
    "hub",
    "ac_type",
}


def _hub_order(sort_col: str) -> str:
    if sort_col in ("destination", "aircraft", "hub", "dest_country", "ac_type"):
        return f"{sort_col} COLLATE NOCASE ASC"
    return f"{sort_col} DESC"


AC_SORT = {"profit_per_ac_day", "contribution", "destination", "hub"}


def _ac_order(sort_col: str) -> str:
    if sort_col in ("destination", "hub"):
        return f"{sort_col} COLLATE NOCASE ASC"
    return f"{sort_col} DESC"


ROUTE_SORT = {
    "profit_per_ac_day",
    "contribution",
    "flight_time_hrs",
    "trips_per_day",
    "shortname",
}


def _route_order(sort_col: str) -> str:
    if sort_col == "shortname":
        return "ac.shortname COLLATE NOCASE ASC"
    return f"ra.{sort_col} DESC"


CONTRIB_SORT = {
    "contribution",
    "profit_per_ac_day",
    "contrib_ratio",
    "hub",
    "destination",
    "aircraft",
}


def _contrib_order(sort_col: str) -> str:
    if sort_col in ("hub", "destination", "aircraft"):
        return f"{sort_col} COLLATE NOCASE ASC"
    return f"{sort_col} DESC"


def _truthy_stopover_hide(v: str) -> bool:
    return v in ("1", "on", "true", "yes")


_FIELD_ID_OK = re.compile(r"^[a-zA-Z][\w\-]*$")


def _safe_field_id(field_id: str, default: str = "hub_iata") -> str:
    fid = (field_id or default).strip()
    return fid if _FIELD_ID_OK.fullmatch(fid) else default


def _search_term_airports(q: str, hub_iata: str, destination_iata: str) -> str:
    for raw in (q, hub_iata, destination_iata):
        t = (raw or "").strip()
        if t:
            return t
    return ""


def _query_flag_on(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "on", "yes")


def _airline_est_profit_from_my_routes(conn: sqlite3.Connection) -> float:
    row = fetch_one(
        conn,
        """
        WITH best AS (
            SELECT origin_id, dest_id, aircraft_id, MAX(profit_per_ac_day) AS p
            FROM route_aircraft
            WHERE is_valid = 1
            GROUP BY origin_id, dest_id, aircraft_id
        )
        SELECT COALESCE(SUM(mr.num_assigned * best.p), 0) AS est
        FROM my_routes mr
        JOIN best ON best.origin_id = mr.origin_id
            AND best.dest_id = mr.dest_id
            AND best.aircraft_id = mr.aircraft_id
        """,
    )
    return float(row["est"] or 0) if row else 0.0


def _my_fleet_rows(conn: sqlite3.Connection) -> list[dict]:
    return fetch_all(
        conn,
        """
        SELECT v.id,
               v.aircraft_id,
               v.shortname,
               v.ac_name,
               v.ac_type,
               v.quantity,
               v.notes,
               COALESCE(v.cost, 0) AS unit_cost,
               COALESCE(ass.assigned, 0) AS assigned,
               CASE
                   WHEN v.quantity > COALESCE(ass.assigned, 0)
                   THEN v.quantity - COALESCE(ass.assigned, 0)
                   ELSE 0
               END AS free,
               v.quantity * COALESCE(v.cost, 0) AS total_value
        FROM v_my_fleet v
        LEFT JOIN (
            SELECT aircraft_id, SUM(num_assigned) AS assigned
            FROM my_routes
            GROUP BY aircraft_id
        ) ass ON ass.aircraft_id = v.aircraft_id
        ORDER BY v.shortname COLLATE NOCASE
        """,
    )


def _my_routes_rows(conn: sqlite3.Connection) -> list[dict]:
    return fetch_all(
        conn,
        """
        SELECT v.id,
               v.hub,
               v.destination,
               v.aircraft,
               v.hub_name,
               v.hub_country,
               v.dest_name,
               v.dest_fullname,
               v.dest_country,
               v.num_assigned,
               v.notes,
               best.p AS profit_per_ac_day,
               best.dkm AS distance_km
        FROM v_my_routes v
        LEFT JOIN (
            SELECT origin_id, dest_id, aircraft_id,
                   MAX(profit_per_ac_day) AS p,
                   MAX(distance_km) AS dkm
            FROM route_aircraft
            WHERE is_valid = 1
            GROUP BY origin_id, dest_id, aircraft_id
        ) best ON best.origin_id = v.origin_id
            AND best.dest_id = v.dest_id
            AND best.aircraft_id = v.aircraft_id
        ORDER BY v.hub COLLATE NOCASE, v.destination COLLATE NOCASE, v.aircraft COLLATE NOCASE
        """,
    )
