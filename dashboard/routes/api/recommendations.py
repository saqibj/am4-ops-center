"""Fleet plan, contributions, heatmap."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.core.vip_pricing import adjust_rows_for_route_type
from app.services.hubs import SQL_EXPLORER_HUB_IATAS

from commands.fleet_recommend import fleet_recommend_rows
from core.game_mode import is_realism
from dashboard.db import HTML_DB_NOT_FOUND, fetch_all, fetch_one, get_read_conn
from dashboard.server import templates

from dashboard.routes.api.shared import (
    CONTRIB_SORT,
    _contrib_order,
    apply_user_assignment_profit_to_catalog_rows,
    _query_flag_on,
)

router = APIRouter()

_ROUTE_TYPE_LABELS = {
    "pax": "Passenger",
    "vip": "VIP",
    "cargo": "Cargo",
    "charter": "Charter",
}


def _heatmap_destination_rows(conn, origin_id: int, top_n: int) -> list[dict]:
    """Top ``top_n`` destinations by best per-aircraft profit at origin (VIP-adjusted when in ``my_routes``)."""
    sql = """
        SELECT ra.dest_id,
               ra.profit_per_ac_day,
               ra.distance_km,
               ra.config_y, ra.config_j, ra.config_f,
               ra.profit_per_trip,
               ra.trips_per_day,
               ra.income AS trip_income,
               ra.contribution,
               ra.income_per_ac_day,
               LOWER(TRIM(mr.route_type)) AS user_route_type
        FROM route_aircraft ra
        LEFT JOIN my_routes mr ON mr.origin_id = ra.origin_id
            AND mr.dest_id = ra.dest_id
            AND mr.aircraft_id = ra.aircraft_id
        WHERE ra.is_valid = 1 AND ra.origin_id = ?
    """
    raw = fetch_all(conn, sql, [origin_id])
    adjusted = apply_user_assignment_profit_to_catalog_rows(raw, conn)
    best: dict[int, float] = {}
    for r in adjusted:
        did = int(r["dest_id"])
        p = float(r.get("profit_per_ac_day") or 0)
        if did not in best or p > best[did]:
            best[did] = p
    ranked = sorted(best.items(), key=lambda x: -x[1])[:top_n]
    dest_ids = [d for d, _ in ranked]
    if not dest_ids:
        return []
    ph = ",".join(["?"] * len(dest_ids))
    airports = fetch_all(
        conn,
        f"""
        SELECT id, iata, name, lat, lng
        FROM airports
        WHERE id IN ({ph}) AND lat IS NOT NULL AND lng IS NOT NULL
        """,
        dest_ids,
    )
    by_id = {int(a["id"]): a for a in airports}
    profit_by_dest = dict(ranked)
    out: list[dict] = []
    for did in dest_ids:
        if did not in by_id:
            continue
        a = by_id[did]
        out.append(
            {
                "iata": a["iata"],
                "name": a.get("name") or "",
                "lat": a["lat"],
                "lng": a["lng"],
                "profit_per_ac_day": profit_by_dest.get(did, 0.0),
            }
        )
    return out


def _parse_optional_float(s: str | None) -> float | None:
    if s is None or str(s).strip() == "":
        return None
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def _parse_buy_next_budget(budget: str | None) -> tuple[int | None, str | None]:
    """Parse budget from query string.

    Returns (value, error_code) where error_code is one of:
    - "missing" for empty input
    - "invalid" for non-numeric or negative input
    """
    if budget is None or str(budget).strip() == "":
        return None, "missing"
    try:
        val = int(float(str(budget).strip()))
    except (TypeError, ValueError):
        return None, "invalid"
    if val < 0:
        return None, "invalid"
    return val, None


_ALLOWED_ROUTE_TYPES = frozenset({"pax", "vip", "cargo", "charter"})


def _normalize_buy_next_route_type(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in _ALLOWED_ROUTE_TYPES:
        return s
    return "pax"


def _aircraft_type_filter_for_route_type(route_type: str) -> str | None:
    """Map route mode to ``aircraft.type`` SQL filter (PAX vs CARGO)."""
    rt = (route_type or "pax").strip().lower()
    if rt == "cargo":
        return "CARGO"
    if rt in ("pax", "vip", "charter"):
        return "PAX"
    return "PAX"


def _recompute_buy_next_profit_yield(rows: list[dict]) -> None:
    for r in rows:
        cost = int(r.get("ac_cost") or 0)
        profit_day = float(r.get("profit_per_ac_day") or 0.0)
        r["profit_yield"] = (profit_day * 1000000.0 / cost) if cost > 0 else 0.0


def _sort_buy_next_rows_inplace(rows: list[dict], sort_val: str) -> None:
    """Mirror SQL ``ORDER BY`` after VIP profit overrides (``total_desc`` uses enrich + finalize)."""
    if sort_val == "total_desc":
        return

    def dest_key(r: dict) -> str:
        return str(r.get("destination") or "").lower()

    def hub_key(r: dict) -> str:
        return str(r.get("hub_iata") or "").lower()

    if sort_val == "price_desc":
        rows.sort(
            key=lambda r: (
                -int(r.get("ac_cost") or 0),
                -float(r.get("profit_per_ac_day") or 0.0),
                dest_key(r),
                hub_key(r),
            )
        )
    elif sort_val == "price_asc":
        rows.sort(
            key=lambda r: (
                int(r.get("ac_cost") or 0),
                -float(r.get("profit_per_ac_day") or 0.0),
                dest_key(r),
                hub_key(r),
            )
        )
    elif sort_val == "profit_desc":
        rows.sort(
            key=lambda r: (
                -float(r.get("profit_per_ac_day") or 0.0),
                -int(r.get("ac_cost") or 0),
                dest_key(r),
                hub_key(r),
            )
        )
    elif sort_val == "profit_asc":
        rows.sort(
            key=lambda r: (
                float(r.get("profit_per_ac_day") or 0.0),
                int(r.get("ac_cost") or 0),
                dest_key(r),
                hub_key(r),
            )
        )
    elif sort_val == "yield_desc":
        rows.sort(
            key=lambda r: (
                -float(r.get("profit_yield") or 0.0),
                -float(r.get("profit_per_ac_day") or 0.0),
                -int(r.get("ac_cost") or 0),
                hub_key(r),
            )
        )


def _exclude_owned_from_request(request: Request) -> bool:
    vals = request.query_params.getlist("exclude_owned")
    if not vals:
        return True
    return "1" in vals


def _buy_next_sort_clause(sort: str) -> str:
    sort_map = {
        "price_desc": "ac.cost DESC, ra.profit_per_ac_day DESC, a_dest.iata COLLATE NOCASE ASC, a_orig.iata COLLATE NOCASE ASC",
        "price_asc": "ac.cost ASC, ra.profit_per_ac_day DESC, a_dest.iata COLLATE NOCASE ASC, a_orig.iata COLLATE NOCASE ASC",
        "profit_desc": "ra.profit_per_ac_day DESC, ac.cost DESC, a_dest.iata COLLATE NOCASE ASC, a_orig.iata COLLATE NOCASE ASC",
        "profit_asc": "ra.profit_per_ac_day ASC, ac.cost ASC, a_dest.iata COLLATE NOCASE ASC, a_orig.iata COLLATE NOCASE ASC",
        "yield_desc": "profit_yield DESC, ra.profit_per_ac_day DESC, ac.cost DESC, a_orig.iata COLLATE NOCASE ASC",
    }
    return sort_map.get(sort, sort_map["price_desc"])


def _buy_next_flat_rows(
    conn,
    *,
    origin_id: int | None,
    budget_val: int,
    sort: str,
    type_filter: str | None,
    route_type: str,
    exclude_owned: bool,
    hide_stopovers: bool,
    hide_existing: bool,
    limit: int,
    filter_dest_id: int | None = None,
    filter_distance_km: float | None = None,
) -> list[dict]:
    # my_routes_collapsed intentionally aggregates multiple aircraft on same OD into one
    # row so highlight doesn't duplicate recommendations.
    sql = """
    WITH my_routes_collapsed AS (
        SELECT origin_id, dest_id,
               MIN(id) AS id,
               MAX(aircraft_id) AS aircraft_id,
               SUM(num_assigned) AS num_assigned
        FROM my_routes
        GROUP BY origin_id, dest_id
    )
    SELECT a_orig.iata AS hub_iata,
           a_dest.iata AS destination,
           a_dest.country AS dest_country,
           a_dest.id AS dest_id,
           ac.id AS aircraft_id,
           ac.shortname AS ac_shortname,
           ac.name AS ac_name,
           ac.type AS ac_type,
           ac.cost AS ac_cost,
           ac.capacity AS ac_capacity,
           ac.range_km AS ac_range,
           ra.distance_km,
           ra.config_y, ra.config_j, ra.config_f,
           ra.income AS income_per_trip,
           ra.profit_per_trip,
           ra.trips_per_day,
           ra.profit_per_ac_day,
           ra.flight_time_hrs,
           ra.needs_stopover,
           ra.stopover_iata,
           CASE WHEN ac.cost > 0
                THEN (ra.profit_per_ac_day * 1000000.0 / ac.cost)
                ELSE 0
           END AS profit_yield,
           mr.id AS my_route_id,
           mr.aircraft_id AS my_route_ac_id,
           current_ac.shortname AS current_ac_shortname,
           current_ac.name AS current_ac_name,
           mr.num_assigned AS current_num_assigned,
           EXISTS (
               SELECT 1 FROM my_routes mr_exact
               WHERE mr_exact.origin_id = ra.origin_id
                 AND mr_exact.dest_id = ra.dest_id
                 AND mr_exact.aircraft_id = ra.aircraft_id
           ) AS is_exact_match
    FROM route_aircraft ra
    JOIN aircraft ac ON ra.aircraft_id = ac.id
    JOIN airports a_orig ON ra.origin_id = a_orig.id
    JOIN airports a_dest ON ra.dest_id = a_dest.id
    LEFT JOIN my_routes_collapsed mr ON mr.origin_id = ra.origin_id AND mr.dest_id = ra.dest_id
    LEFT JOIN aircraft current_ac ON mr.aircraft_id = current_ac.id
    WHERE ra.is_valid = 1
    """
    origin_sql = ""
    params: list = []
    if origin_id is not None:
        origin_sql = " AND ra.origin_id = ?"
        params.append(origin_id)
    sql += origin_sql
    if filter_dest_id is not None:
        sql += " AND ra.dest_id = ?"
        params.append(filter_dest_id)
    if filter_distance_km is not None:
        sql += " AND ra.distance_km IS NOT NULL AND ABS(ra.distance_km - ?) <= 1.0"
        params.append(filter_distance_km)
    sql += """
      AND ac.cost > 0
      AND ac.cost <= ?
      AND ra.profit_per_ac_day > 0
    """
    params.append(budget_val)
    if type_filter:
        sql += " AND UPPER(TRIM(ac.type)) = UPPER(TRIM(?))"
        params.append(type_filter)
    if hide_stopovers:
        sql += " AND COALESCE(ra.needs_stopover, 0) = 0"
    if exclude_owned:
        sql += """
        AND NOT EXISTS (
            SELECT 1 FROM my_fleet mf
            WHERE mf.aircraft_id = ac.id AND COALESCE(mf.quantity, 0) > 0
        )
        """
    if hide_existing:
        sql += " AND mr.id IS NULL"

    fetch_limit = limit * 5 if sort == "total_desc" else limit
    if route_type == "vip":
        fetch_limit = min(2000, fetch_limit * 15)
    sql += f" ORDER BY {_buy_next_sort_clause(sort)} LIMIT ?"
    params.append(fetch_limit)
    return fetch_all(conn, sql, params)


def _enrich_buy_next_rows(rows: list[dict], budget_val: int) -> None:
    for r in rows:
        cost = int(r.get("ac_cost") or 0)
        profit_day = float(r.get("profit_per_ac_day") or 0.0)
        qty = (int(budget_val) // cost) if cost > 0 else 0
        total_day = qty * profit_day
        payback_days = round(cost / profit_day, 1) if profit_day > 0 else None
        r["qty_affordable"] = qty
        r["total_daily_profit"] = total_day
        r["payback_days"] = payback_days
        if int(r.get("is_exact_match") or 0):
            r["match_tier"] = "exact"
        elif r.get("my_route_id") is not None:
            r["match_tier"] = "route"
        else:
            r["match_tier"] = "none"
        r["is_best_buy"] = False


def _finalize_buy_next_rows(
    rows: list[dict], sort_val: str, limit: int
) -> tuple[list[dict], bool]:
    if sort_val == "total_desc":
        rows.sort(
            key=lambda r: (
                float(r.get("total_daily_profit") or 0.0),
                float(r.get("profit_per_ac_day") or 0.0),
            ),
            reverse=True,
        )
    truncated = len(rows) >= limit
    rows = rows[:limit]
    if rows:
        best_idx = max(
            range(len(rows)),
            key=lambda i: float(rows[i].get("total_daily_profit") or 0.0),
        )
        rows[best_idx]["is_best_buy"] = True
    return rows, truncated


def _allocation_hub_iatas(conn) -> list[str]:
    """Managed hubs with a successful extract (same scope as Hub Explorer)."""
    rows = fetch_all(conn, SQL_EXPLORER_HUB_IATAS)
    return [str(r["iata"]).strip() for r in rows if r.get("iata")]


def _hub_queue_for_aircraft(
    conn, aircraft_id: int, origin_id: int, limit: int
) -> list[dict]:
    return fetch_all(
        conn,
        """
        SELECT ra.profit_per_ac_day,
               a_dest.iata AS dest,
               ra.config_y, ra.config_j, ra.config_f,
               a_orig.iata AS hub
        FROM route_aircraft ra
        JOIN airports a_dest ON ra.dest_id = a_dest.id
        JOIN airports a_orig ON ra.origin_id = a_orig.id
        WHERE ra.is_valid = 1 AND ra.aircraft_id = ? AND ra.origin_id = ?
        ORDER BY ra.profit_per_ac_day DESC
        LIMIT ?
        """,
        [aircraft_id, origin_id, limit],
    )


def _greedy_multi_hub_allocate(
    conn,
    *,
    aircraft_id: int,
    quantity: int,
    hub_iatas: list[str],
) -> tuple[list[dict], list[str]]:
    """Return (picks ordered by assignment, warnings). Each pick adds one aircraft-day route."""
    warnings: list[str] = []
    scope = [h.strip() for h in hub_iatas if h and str(h).strip()]
    if not scope:
        scope = _allocation_hub_iatas(conn)
    if not scope:
        return [], ["No hub scope: add hubs under Hub Manager and run a successful extract."]

    queues: dict[int, list[dict]] = {}
    for raw_iata in scope:
        hub_row = fetch_one(
            conn,
            "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
            [raw_iata],
        )
        if not hub_row:
            warnings.append(f"Unknown hub {raw_iata!r} skipped.")
            continue
        oid = int(hub_row["id"])
        if oid in queues:
            continue
        q = _hub_queue_for_aircraft(conn, aircraft_id, oid, quantity)
        if not q:
            continue
        queues[oid] = q

    if not queues:
        return [], warnings + ["No valid routes for this aircraft at the selected hubs."]

    ptr = {oid: 0 for oid in queues}
    remaining = quantity
    picks: list[dict] = []
    while remaining > 0:
        best_oid: int | None = None
        best_p = -1e18
        for oid, q in queues.items():
            i = ptr[oid]
            if i >= len(q):
                continue
            p = float(q[i]["profit_per_ac_day"] or 0)
            if p > best_p:
                best_p = p
                best_oid = oid
        if best_oid is None:
            break
        row = queues[best_oid][ptr[best_oid]]
        ptr[best_oid] += 1
        picks.append(
            {
                "hub": str(row["hub"] or ""),
                "dest": str(row["dest"] or ""),
                "profit_per_ac_day": best_p,
                "config_y": row.get("config_y"),
                "config_j": row.get("config_j"),
                "config_f": row.get("config_f"),
            }
        )
        remaining -= 1

    if quantity > len(picks):
        warnings.append(
            f"Allocated {len(picks)} of {quantity} requested (not enough distinct top routes across hubs)."
        )
    return picks, warnings


def _buy_next_top_routes(
    conn,
    aircraft_id: int,
    origin_id: int | None,
) -> list[dict]:
    sql = """
    SELECT a_dest.iata AS destination, a_dest.country AS dest_country,
           a_orig.iata AS hub,
           ra.distance_km,
           ra.config_y, ra.config_j, ra.config_f,
           ra.profit_per_trip, ra.trips_per_day, ra.profit_per_ac_day,
           ra.flight_time_hrs, ra.needs_stopover
    FROM route_aircraft ra
    JOIN airports a_orig ON ra.origin_id = a_orig.id
    JOIN airports a_dest ON ra.dest_id = a_dest.id
    WHERE ra.is_valid = 1 AND ra.aircraft_id = ?
    """
    params: list = [aircraft_id]
    if origin_id is not None:
        sql += " AND ra.origin_id = ?"
        params.append(origin_id)
    sql += " ORDER BY ra.profit_per_ac_day DESC LIMIT 3"
    return fetch_all(conn, sql, params)


@router.get("/buy-next", response_class=HTMLResponse)
def api_buy_next(
    request: Request,
    hub: str = Query(""),
    budget: str | None = Query(None),
    sort: str = Query("price_desc"),
    route_type: str = Query("pax"),
    exclude_owned: int = Query(0),
    hide_stopovers: int = Query(0),
    hide_existing: int = Query(0),
    limit: int = Query(15, ge=1, le=500),
    filter_dest: str = Query(""),
    filter_distance_km: str = Query(""),
):
    allowed_sorts = {
        "price_desc",
        "price_asc",
        "profit_desc",
        "profit_asc",
        "yield_desc",
        "total_desc",
    }
    sort_val = sort if sort in allowed_sorts else "price_desc"
    budget_val, budget_err = _parse_buy_next_budget(budget)
    route_rt = _normalize_buy_next_route_type(route_type)
    type_filter = _aircraft_type_filter_for_route_type(route_rt)
    exclude_owned_flag = _query_flag_on(str(exclude_owned))
    hide_stopovers_flag = _query_flag_on(str(hide_stopovers))
    hide_existing_flag = _query_flag_on(str(hide_existing))

    if not hub.strip():
        return HTMLResponse(
            "<p class='am4-text-secondary'>Pick a hub and enter a budget.</p>"
        )
    if budget_err == "missing":
        return HTMLResponse(
            "<p class='am4-text-secondary'>Pick a hub and enter a budget.</p>"
        )
    if budget_err == "invalid" or budget_val is None:
        return HTMLResponse("<p class='text-amber-400'>Enter a valid budget.</p>")

    try:
        conn = get_read_conn()
    except FileNotFoundError:
        return HTMLResponse(
            HTML_DB_NOT_FOUND
        )

    try:
        hub_row = fetch_one(
            conn,
            "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
            [hub.strip()],
        )
        if not hub_row:
            return HTMLResponse("<p class='text-amber-400'>Unknown hub.</p>")
        origin_id = int(hub_row["id"])

        filter_dest_id: int | None = None
        fd = (filter_dest or "").strip()
        if fd:
            dest_row = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [fd],
            )
            if not dest_row:
                return HTMLResponse("<p class='text-amber-400'>Unknown destination filter.</p>")
            filter_dest_id = int(dest_row["id"])

        filter_dist = _parse_optional_float(filter_distance_km)

        rows = _buy_next_flat_rows(
            conn,
            origin_id=origin_id,
            budget_val=int(budget_val),
            sort=sort_val,
            type_filter=type_filter,
            route_type=route_rt,
            exclude_owned=exclude_owned_flag,
            hide_stopovers=hide_stopovers_flag,
            hide_existing=hide_existing_flag,
            limit=limit,
            filter_dest_id=filter_dest_id,
            filter_distance_km=filter_dist,
        )
        if route_rt == "vip":
            rows = adjust_rows_for_route_type(rows, "vip", is_realism(conn))
            _recompute_buy_next_profit_yield(rows)
            _sort_buy_next_rows_inplace(rows, sort_val)
        _enrich_buy_next_rows(rows, int(budget_val))
        rows, truncated = _finalize_buy_next_rows(rows, sort_val, limit)

        return templates.TemplateResponse(
            request,
            "partials/buy_next_results.html",
            {
                "rows": rows,
                "sort": sort_val,
                "budget": int(budget_val),
                "hub": hub.strip().upper(),
                "truncated": truncated,
                "limit": limit,
                "route_type": route_rt,
                "route_type_label": _ROUTE_TYPE_LABELS.get(route_rt, route_rt),
            },
        )
    finally:
        conn.close()


@router.get("/buy-next-global", response_class=HTMLResponse)
def api_buy_next_global(
    request: Request,
    budget: str | None = Query(None),
    sort: str = Query("total_desc"),
    route_type: str = Query("pax"),
    exclude_owned: int = Query(0),
    hide_stopovers: int = Query(0),
    hide_existing: int = Query(0),
    limit: int = Query(15, ge=1, le=100),
):
    """Flat buy-next across all hubs (hub column in results). Max limit 100."""
    allowed_sorts = {
        "price_desc",
        "price_asc",
        "profit_desc",
        "profit_asc",
        "yield_desc",
        "total_desc",
    }
    sort_val = sort if sort in allowed_sorts else "total_desc"
    budget_val, budget_err = _parse_buy_next_budget(budget)
    route_rt = _normalize_buy_next_route_type(route_type)
    type_filter = _aircraft_type_filter_for_route_type(route_rt)
    exclude_owned_flag = _query_flag_on(str(exclude_owned))
    hide_stopovers_flag = _query_flag_on(str(hide_stopovers))
    hide_existing_flag = _query_flag_on(str(hide_existing))

    if budget_err == "missing":
        return HTMLResponse(
            "<p class='am4-text-secondary'>Enter a budget to browse globally.</p>"
        )
    if budget_err == "invalid" or budget_val is None:
        return HTMLResponse("<p class='text-amber-400'>Enter a valid budget.</p>")

    try:
        conn = get_read_conn()
    except FileNotFoundError:
        return HTMLResponse(
            HTML_DB_NOT_FOUND
        )

    try:
        rows = _buy_next_flat_rows(
            conn,
            origin_id=None,
            budget_val=int(budget_val),
            sort=sort_val,
            type_filter=type_filter,
            route_type=route_rt,
            exclude_owned=exclude_owned_flag,
            hide_stopovers=hide_stopovers_flag,
            hide_existing=hide_existing_flag,
            limit=limit,
        )
        if route_rt == "vip":
            rows = adjust_rows_for_route_type(rows, "vip", is_realism(conn))
            _recompute_buy_next_profit_yield(rows)
            _sort_buy_next_rows_inplace(rows, sort_val)
        _enrich_buy_next_rows(rows, int(budget_val))
        rows, truncated = _finalize_buy_next_rows(rows, sort_val, limit)

        return templates.TemplateResponse(
            request,
            "partials/buy_next_global_results.html",
            {
                "rows": rows,
                "sort": sort_val,
                "budget": int(budget_val),
                "truncated": truncated,
                "limit": limit,
                "route_type": route_rt,
                "route_type_label": _ROUTE_TYPE_LABELS.get(route_rt, route_rt),
            },
        )
    finally:
        conn.close()


@router.get("/buy-next/allocate", response_class=HTMLResponse)
def api_buy_next_allocate(
    request: Request,
    aircraft_id: int = Query(..., ge=1),
    quantity: int = Query(1, ge=1, le=50),
    hubs: list[str] = Query(default=[]),
):
    """Greedy split of N copies across hubs by best marginal profit_per_ac_day per copy."""
    try:
        conn = get_read_conn()
    except FileNotFoundError:
        return HTMLResponse(
            HTML_DB_NOT_FOUND
        )

    try:
        ac = fetch_one(
            conn,
            "SELECT id, shortname, name, cost FROM aircraft WHERE id = ?",
            [aircraft_id],
        )
        if not ac:
            return HTMLResponse("<p class='text-amber-400'>Unknown aircraft.</p>")

        cost = int(ac["cost"] or 0)
        picks, warnings = _greedy_multi_hub_allocate(
            conn,
            aircraft_id=aircraft_id,
            quantity=quantity,
            hub_iatas=hubs,
        )

        total_daily = sum(float(p["profit_per_ac_day"] or 0) for p in picks)
        n_alloc = len(picks)
        capital_requested = cost * quantity
        capital_placed = cost * n_alloc
        payback_days = (
            round(capital_placed / total_daily, 1) if total_daily > 1e-9 else None
        )

        by_hub: dict[str, list[dict]] = {}
        for p in picks:
            h = str(p["hub"] or "?")
            by_hub.setdefault(h, []).append(p)

        hub_summary = [
            {
                "hub": h,
                "copies": len(lst),
                "daily": sum(float(x["profit_per_ac_day"] or 0) for x in lst),
                "routes": lst,
            }
            for h, lst in sorted(by_hub.items(), key=lambda x: -sum(float(y["profit_per_ac_day"] or 0) for y in x[1]))
        ]

        return templates.TemplateResponse(
            request,
            "partials/buy_next_allocate.html",
            {
                "aircraft_id": aircraft_id,
                "shortname": ac["shortname"],
                "name": ac["name"],
                "quantity_requested": quantity,
                "quantity_allocated": n_alloc,
                "cost": cost,
                "capital_requested": capital_requested,
                "capital_placed": capital_placed,
                "total_daily": total_daily,
                "payback_days": payback_days,
                "picks": picks,
                "hub_summary": hub_summary,
                "warnings": warnings,
            },
        )
    finally:
        conn.close()


@router.get("/fleet-plan", response_class=HTMLResponse)
def api_fleet_plan(
    request: Request,
    hub: str = Query(""),
    budget: int = Query(200_000_000, ge=0),
    top_n: int = Query(15, ge=1, le=100),
    hide_owned: str = Query(""),
):
    if not hub.strip():
        return HTMLResponse("<p class='am4-text-secondary'>Select a hub.</p>")

    conn = get_read_conn()
    try:
        rows, err = fleet_recommend_rows(
            conn,
            hub.strip(),
            int(budget),
            int(top_n),
            hide_owned=_query_flag_on(hide_owned),
        )
    finally:
        conn.close()

    if err == "unknown_hub":
        return HTMLResponse("<p class='text-amber-400'>Unknown hub.</p>")

    return templates.TemplateResponse(
        request,
        "partials/fleet_plan_table.html",
        {"rows": rows},
    )


@router.get("/contributions", response_class=HTMLResponse)
def api_contributions(
    request: Request,
    hub: str = Query(""),
    ac_type: str = Query(""),
    min_contribution: float = Query(0.0),
    limit: int = Query(500, ge=10, le=5000),
    sort: str = Query("contribution"),
):
    sort_col = sort if sort in CONTRIB_SORT else "contribution"
    inner = """
        SELECT *,
            CASE
                WHEN profit_per_ac_day IS NOT NULL AND ABS(profit_per_ac_day) > 1e-9
                THEN contribution / profit_per_ac_day
                ELSE NULL
            END AS contrib_ratio
        FROM v_best_routes
        WHERE contribution >= ?
    """
    params: list = [min_contribution]
    if hub.strip():
        inner += " AND hub = ?"
        params.append(hub.strip())
    if ac_type.strip():
        inner += " AND UPPER(ac_type) = UPPER(?)"
        params.append(ac_type.strip())
    order_sql = _contrib_order(sort_col)
    query = f"SELECT * FROM ({inner}) AS t ORDER BY {order_sql} LIMIT ?"
    params.append(limit)

    conn = get_read_conn()
    try:
        rows = fetch_all(conn, query, params)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/contributions_table.html",
        {"rows": rows, "sort": sort_col},
    )


@router.get("/heatmap-data")
def api_heatmap_data(hub: str = Query(""), top_n: int = Query(100, ge=10, le=500)) -> list[dict]:
    if not hub.strip():
        return []
    hub_iata = hub.strip().upper()

    try:
        conn = get_read_conn()
    except FileNotFoundError:
        return []
    try:
        hub_row = fetch_one(
            conn,
            "SELECT id FROM airports WHERE iata = ? LIMIT 1",
            [hub_iata],
        )
        if not hub_row:
            return []
        origin_id = int(hub_row["id"])
        rows = _heatmap_destination_rows(conn, origin_id, top_n)
    finally:
        conn.close()

    profits = [float(r["profit_per_ac_day"] or 0) for r in rows]
    p_min, p_max = (min(profits), max(profits)) if profits else (0.0, 1.0)
    span = p_max - p_min if p_max > p_min else 1.0

    out = []
    for r in rows:
        p = float(r["profit_per_ac_day"] or 0)
        t = (p - p_min) / span
        out.append(
            {
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
                "iata": r["iata"],
                "name": r["name"] or "",
                "profit": p,
                "aircraft": "",
                "t": t,
            }
        )
    return out


@router.get("/heatmap-panel", response_class=HTMLResponse)
def api_heatmap_panel(request: Request, hub: str = Query(""), top_n: int = Query(100, ge=10, le=500)):
    """HTML+script panel driven by /api/heatmap-data JSON (same shape as inline markers)."""
    if not hub.strip():
        return HTMLResponse("<p class='am4-text-secondary p-4'>Select a hub.</p>")
    hub_iata = hub.strip().upper()

    conn = get_read_conn()
    try:
        hub_row = fetch_one(
            conn,
            "SELECT id FROM airports WHERE iata = ? LIMIT 1",
            [hub_iata],
        )
        if not hub_row:
            return HTMLResponse("<p class='am4-text-secondary p-4'>Unknown hub.</p>")
        origin_id = int(hub_row["id"])
        rows = _heatmap_destination_rows(conn, origin_id, top_n)
    finally:
        conn.close()

    if not rows:
        return HTMLResponse("<p class='am4-text-secondary p-4'>No geocoded destinations for this hub.</p>")

    profits = [float(r["profit_per_ac_day"] or 0) for r in rows]
    p_min, p_max = min(profits), max(profits)
    span = p_max - p_min if p_max > p_min else 1.0
    markers = []
    for r in rows:
        p = float(r["profit_per_ac_day"] or 0)
        t = (p - p_min) / span
        markers.append(
            {
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
                "iata": r["iata"],
                "name": r["name"] or "",
                "profit": p,
                "aircraft": "",
                "t": t,
            }
        )
    payload = json.dumps(markers)
    html = f"""
<div class="rounded-lg am4-bordered overflow-hidden">
  <div id="ops-center-leaflet-map" class="h-[600px] w-full am4-sunken"></div>
</div>
<script type="application/json" id="ops-center-leaflet-data">{payload}</script>
<script>
(function() {{
  const el = document.getElementById("ops-center-leaflet-map");
  const raw = document.getElementById("ops-center-leaflet-data");
  if (!el || !raw) return;
  const markers = JSON.parse(raw.textContent);
  if (window.__opsCenterMap) {{
    try {{ window.__opsCenterMap.remove(); }} catch (e) {{}}
    window.__opsCenterMap = null;
  }}
  const center = markers.length ? [markers[0].lat, markers[0].lng] : [20, 0];
  const map = L.map(el).setView(center, markers.length ? 4 : 2);
  window.__opsCenterMap = map;
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; CartoDB',
  }}).addTo(map);
  function color(t) {{
    const r = Math.round(255 * (1 - t));
    const g = Math.round(200 * t);
    return `rgb(${{r}},${{g}},80)`;
  }}
  const bounds = [];
  markers.forEach(m => {{
    const c = color(m.t);
    const mk = L.circleMarker([m.lat, m.lng], {{
      radius: 8,
      fillColor: c,
      color: '#1f2937',
      weight: 1,
      fillOpacity: 0.85,
    }}).addTo(map);
    const popupEl = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = m.iata;
    popupEl.appendChild(title);
    if (m.name) {{
      popupEl.appendChild(document.createTextNode(' (' + m.name + ')'));
    }}
    popupEl.appendChild(document.createElement('br'));
    popupEl.appendChild(
      document.createTextNode('Profit/day: $' + Math.round(m.profit).toLocaleString())
    );
    popupEl.appendChild(document.createElement('br'));
    const small = document.createElement('span');
    small.className = 'am4-text-muted text-xs';
    small.textContent = (m.aircraft || '').slice(0, 120);
    popupEl.appendChild(small);
    mk.bindPopup(popupEl);
    bounds.push([m.lat, m.lng]);
  }});
  if (bounds.length) map.fitBounds(bounds, {{ padding: [40, 40], maxZoom: 8 }});
}})();
</script>
<p class="am4-text-secondary text-sm mt-2">{len(markers)} destinations (top by best aircraft profit).</p>
"""
    return HTMLResponse(html)
