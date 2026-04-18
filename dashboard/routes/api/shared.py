"""Shared helpers and extraction lock for /api/* route modules."""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from app.core.vip_pricing import adjust_rows_for_route_type
from core.game_mode import is_realism
from dashboard.db import fetch_all, fetch_one
from dashboard.hub_freshness import STALE_AFTER_DAYS
from database.my_routes_dao import ALLOWED_ROUTE_TYPES

_ROUTE_TYPE_LABELS = {
    "pax": "PAX",
    "vip": "VIP",
    "cargo": "Cargo",
    "charter": "Charter",
}


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


def _parse_my_routes_type_filter(raw: str | None) -> str | None:
    """Return allowed route type or None (no filter)."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    return s if s in ALLOWED_ROUTE_TYPES else None


def _airline_est_profit_from_my_routes(
    conn: sqlite3.Connection,
    route_type_filter: str | None = None,
) -> float:
    """Sum ``num_assigned * profit_per_ac_day`` with VIP rows using VIP-adjusted profit."""
    rows = _my_routes_rows(conn, route_type_filter=route_type_filter)
    total = 0.0
    for r in rows:
        n = float(r.get("num_assigned") or 0)
        p = r.get("profit_per_ac_day")
        if p is None:
            continue
        total += n * float(p)
    return total


def _my_routes_type_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Count rows per ``route_type`` (unfiltered)."""
    try:
        rows = fetch_all(
            conn,
            """
            SELECT LOWER(TRIM(COALESCE(route_type, 'pax'))) AS rt, COUNT(*) AS c
            FROM my_routes
            GROUP BY LOWER(TRIM(COALESCE(route_type, 'pax')))
            """,
        )
    except sqlite3.OperationalError:
        return {}
    out: dict[str, int] = {k: 0 for k in sorted(ALLOWED_ROUTE_TYPES)}
    for row in rows:
        rt = (row["rt"] or "pax").strip().lower()
        if rt not in out:
            rt = "pax"
        out[rt] = int(row["c"] or 0)
    return out


def _my_routes_summary_stats(
    conn: sqlite3.Connection,
    route_type_filter: str | None = None,
) -> dict:
    """Row counts, assigned sum, estimated profit, and type breakdown for summary cards."""
    filt = _parse_my_routes_type_filter(route_type_filter)
    type_counts = _my_routes_type_counts(conn)
    if filt:
        row = fetch_one(
            conn,
            """
            SELECT COUNT(*) AS nrows, COALESCE(SUM(num_assigned), 0) AS assigned
            FROM my_routes
            WHERE LOWER(TRIM(route_type)) = ?
            """,
            (filt,),
        )
    else:
        row = fetch_one(
            conn,
            """
            SELECT COUNT(*) AS nrows, COALESCE(SUM(num_assigned), 0) AS assigned
            FROM my_routes
            """,
        )
    est = _airline_est_profit_from_my_routes(conn, route_type_filter=filt)
    tc_line = " · ".join(
        f"{_ROUTE_TYPE_LABELS[k]}: {type_counts.get(k, 0)}"
        for k in ("pax", "vip", "cargo", "charter")
    )
    return {
        "nrows": int(row["nrows"] or 0) if row else 0,
        "assigned": int(row["assigned"] or 0) if row else 0,
        "est_profit": est,
        "type_counts": type_counts,
        "type_counts_line": tc_line,
    }


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
               v.engine,
               v.mods,
               v.purchase_price,
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


def _my_routes_rows(
    conn: sqlite3.Connection,
    route_type_filter: str | None = None,
) -> list[dict]:
    """Inventory rows with ``route_type``, display profit (VIP-adjusted when stored type is vip)."""
    filt = _parse_my_routes_type_filter(route_type_filter)
    where = ""
    params: list = []
    if filt:
        where = " WHERE LOWER(TRIM(v.route_type)) = ? "
        params.append(filt)

    sql = f"""
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
               v.needs_extraction_refresh,
               LOWER(TRIM(v.route_type)) AS route_type,
               ra.profit_per_ac_day AS ra_ppad,
               ra.distance_km AS ra_dist,
               ra.profit_per_trip AS ra_ppt,
               ra.trips_per_day AS ra_tpd,
               ra.income AS ra_income,
               ra.config_y AS ra_cy,
               ra.config_j AS ra_cj,
               ra.config_f AS ra_cf
        FROM v_my_routes v
        LEFT JOIN route_aircraft ra
          ON ra.origin_id = v.origin_id
         AND ra.dest_id = v.dest_id
         AND ra.aircraft_id = v.aircraft_id
         AND ra.is_valid = 1
        {where}
        ORDER BY v.hub COLLATE NOCASE, v.destination COLLATE NOCASE, v.aircraft COLLATE NOCASE
    """
    raw = fetch_all(conn, sql, params)
    realism = is_realism(conn)
    out: list[dict] = []
    for row in raw:
        d = dict(row)
        rt = (d.get("route_type") or "pax").strip().lower()
        if rt not in ALLOWED_ROUTE_TYPES:
            rt = "pax"
        d["route_type"] = rt
        d["route_type_label"] = _ROUTE_TYPE_LABELS.get(rt, rt.upper())

        cy, cj, cf = d.get("ra_cy"), d.get("ra_cj"), d.get("ra_cf")
        ra_ppad = d.pop("ra_ppad", None)
        ra_dist = d.pop("ra_dist", None)
        ra_ppt = d.pop("ra_ppt", None)
        ra_tpd = d.pop("ra_tpd", None)
        ra_income = d.pop("ra_income", None)
        d.pop("ra_cy", None)
        d.pop("ra_cj", None)
        d.pop("ra_cf", None)

        d["distance_km"] = ra_dist
        d["profit_per_ac_day"] = ra_ppad

        if (
            rt == "vip"
            and ra_ppad is not None
            and ra_ppt is not None
            and ra_dist is not None
        ):
            vip_row = {
                "distance_km": float(ra_dist),
                "config_y": int(cy or 0),
                "config_j": int(cj or 0),
                "config_f": int(cf or 0),
                "profit_per_trip": float(ra_ppt),
                "income_per_trip": float(ra_income)
                if ra_income is not None
                else None,
                "trips_per_day": int(ra_tpd or 0),
                "profit_per_ac_day": float(ra_ppad),
            }
            adj = adjust_rows_for_route_type([vip_row], "vip", realism)
            if adj:
                d["profit_per_ac_day"] = adj[0].get("profit_per_ac_day")

        out.append(d)
    return out
