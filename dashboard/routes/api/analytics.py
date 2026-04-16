"""Hub explorer, route analyzer, aircraft views, chart JSON."""

from __future__ import annotations

import sqlite3
from html import escape as html_escape

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.db import HTML_DB_NOT_FOUND, fetch_all, fetch_one, get_read_conn
from dashboard.server import templates

from dashboard.routes.api.shared import (
    AC_SORT,
    HUB_SORT_COLUMNS,
    ROUTE_SORT,
    _ac_order,
    _hub_order,
    _route_order,
    _truthy_stopover_hide,
)

router = APIRouter()


@router.get("/hub-routes", response_class=HTMLResponse)
def api_hub_routes(
    request: Request,
    hub: str = Query(""),
    filter_type: str = Query("", alias="type"),
    ac_type: str = Query(""),
    sort: str = Query("profit_per_ac_day"),
    limit: int = Query(50, ge=1, le=5000),
    min_profit: float = Query(0.0),
    max_dist: float = Query(0.0),
    max_flight_hrs: float = Query(0.0),
    hide_stopovers: str = Query(""),
):
    atype = filter_type.strip() or ac_type.strip()
    if not hub.strip():
        return HTMLResponse("<p class='am4-text-secondary'>Select a hub.</p>")

    sort_col = sort if sort in HUB_SORT_COLUMNS else "profit_per_ac_day"
    order_sql = _hub_order(sort_col)

    query = "SELECT * FROM v_best_routes WHERE hub = ?"
    params: list = [hub.strip()]

    if atype:
        query += " AND UPPER(ac_type) = UPPER(?)"
        params.append(atype)

    query += " AND profit_per_ac_day >= ?"
    params.append(min_profit)

    if max_dist > 0:
        query += " AND distance_km <= ?"
        params.append(max_dist)

    if max_flight_hrs > 0:
        query += " AND flight_time_hrs <= ?"
        params.append(max_flight_hrs)

    if _truthy_stopover_hide(hide_stopovers):
        query += " AND needs_stopover = 0"

    query += f" ORDER BY {order_sql} LIMIT ?"
    params.append(limit)

    conn = get_read_conn()
    try:
        routes = fetch_all(conn, query, params)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/route_table.html",
        {"routes": routes, "sort": sort_col},
    )


@router.get("/hub-summary", response_class=HTMLResponse)
def api_hub_summary(
    request: Request,
    hub: str = Query(""),
    filter_type: str = Query("", alias="type"),
    ac_type: str = Query(""),
    min_profit: float = Query(0.0),
    max_dist: float = Query(0.0),
    max_flight_hrs: float = Query(0.0),
    hide_stopovers: str = Query(""),
):
    atype = filter_type.strip() or ac_type.strip()
    if not hub.strip():
        return HTMLResponse("")

    # Aggregate from route_aircraft filtered by origin_id — not FROM v_best_routes. The view joins
    # every row to dest + aircraft; SQLite then planned a path that scanned huge portions of the
    # join (~seconds on multi-million route_aircraft). Filtering by hub after all joins prevents
    # using idx_ra_origin_valid_profit; direct origin_id + is_valid + profit uses a covering seek.
    conn = get_read_conn()
    try:
        origin = fetch_one(
            conn,
            "SELECT id FROM airports WHERE TRIM(iata) = TRIM(?) LIMIT 1",
            [hub.strip()],
        )
        origin_id = int(origin["id"]) if origin else -1

        q = """
            SELECT COUNT(*) AS n,
                   AVG(ra.profit_per_ac_day) AS avg_profit,
                   MAX(ra.profit_per_ac_day) AS best_profit
            FROM route_aircraft ra
        """
        params: list = []
        if atype:
            q += " JOIN aircraft ac ON ra.aircraft_id = ac.id"
        q += """
            WHERE ra.is_valid = 1
              AND ra.origin_id = ?
        """
        params.append(origin_id)
        q += " AND ra.profit_per_ac_day >= ?"
        params.append(min_profit)
        if atype:
            q += " AND UPPER(ac.type) = UPPER(?)"
            params.append(atype)
        if max_dist > 0:
            q += " AND ra.distance_km <= ?"
            params.append(max_dist)
        if max_flight_hrs > 0:
            q += " AND ra.flight_time_hrs <= ?"
            params.append(max_flight_hrs)
        if _truthy_stopover_hide(hide_stopovers):
            q += " AND ra.needs_stopover = 0"

        row = fetch_one(conn, q, params)
    finally:
        conn.close()

    if not row:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request,
        "partials/stats_cards.html",
        {"scope": "hub", "stats": row},
    )


@router.get("/hub-chart", response_class=HTMLResponse)
def api_hub_chart(
    request: Request,
    hub: str = Query(""),
    filter_type: str = Query("", alias="type"),
    ac_type: str = Query(""),
    min_profit: float = Query(0.0),
    max_dist: float = Query(0.0),
    max_flight_hrs: float = Query(0.0),
    hide_stopovers: str = Query(""),
    limit: int = Query(20, ge=5, le=100),
):
    atype = filter_type.strip() or ac_type.strip()
    if not hub.strip():
        return HTMLResponse("<p class='am4-text-secondary text-sm'>Select a hub for the chart.</p>")

    query = """
        SELECT destination, aircraft, profit_per_ac_day FROM v_best_routes
        WHERE hub = ?
    """
    params: list = [hub.strip()]
    if atype:
        query += " AND UPPER(ac_type) = UPPER(?)"
        params.append(atype)
    query += " AND profit_per_ac_day >= ?"
    params.append(min_profit)
    if max_dist > 0:
        query += " AND distance_km <= ?"
        params.append(max_dist)
    if max_flight_hrs > 0:
        query += " AND flight_time_hrs <= ?"
        params.append(max_flight_hrs)
    if _truthy_stopover_hide(hide_stopovers):
        query += " AND needs_stopover = 0"
    query += " ORDER BY profit_per_ac_day DESC LIMIT ?"
    params.append(limit)

    conn = get_read_conn()
    try:
        rows = fetch_all(conn, query, params)
    finally:
        conn.close()

    labels = [f"{r['destination']} ({r['aircraft']})" for r in rows]
    values = [float(r["profit_per_ac_day"] or 0) for r in rows]

    return templates.TemplateResponse(
        request,
        "partials/chart_data.html",
        {
            "chart_id": "hubProfitChart",
            "labels": labels,
            "values": values,
            "label": "Profit/Day ($)",
        },
    )


@router.get("/aircraft-routes", response_class=HTMLResponse)
def api_aircraft_routes(
    request: Request,
    aircraft: str = Query(""),
    min_profit: float = Query(0.0),
    sort: str = Query("profit_per_ac_day"),
    limit: int = Query(200, ge=1, le=5000),
):
    if not aircraft.strip():
        return HTMLResponse("<p class='am4-text-secondary'>Select an aircraft.</p>")

    sort_col = sort if sort in AC_SORT else "profit_per_ac_day"
    order_sql = _ac_order(sort_col)
    sql = f"""
        SELECT * FROM v_best_routes
        WHERE aircraft = ? AND profit_per_ac_day >= ?
        ORDER BY {order_sql}
        LIMIT ?
    """
    conn = get_read_conn()
    try:
        routes = fetch_all(conn, sql, [aircraft.strip(), min_profit, limit])
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/aircraft_table.html",
        {"routes": routes, "sort": sort_col},
    )


@router.get("/aircraft-stats", response_class=HTMLResponse)
def api_aircraft_stats(request: Request, aircraft: str = Query("")):
    if not aircraft.strip():
        return HTMLResponse("")

    conn = get_read_conn()
    try:
        agg = fetch_one(
            conn,
            """
            SELECT COUNT(*) AS viable_routes,
                   AVG(profit_per_ac_day) AS avg_profit,
                   MAX(profit_per_ac_day) AS best_profit
            FROM v_best_routes WHERE aircraft = ?
            """,
            [aircraft.strip()],
        )
        best_hub_row = fetch_one(
            conn,
            """
            SELECT hub FROM v_best_routes WHERE aircraft = ?
            GROUP BY hub ORDER BY MAX(profit_per_ac_day) DESC LIMIT 1
            """,
            [aircraft.strip()],
        )
    finally:
        conn.close()

    if not agg:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request,
        "partials/aircraft_stats.html",
        {
            "agg": agg,
            "best_hub": best_hub_row["hub"] if best_hub_row else "—",
        },
    )


@router.get("/route-destinations", response_class=HTMLResponse)
def api_route_destinations(request: Request, origin: str = Query("")):
    if not origin.strip():
        return HTMLResponse(
            "<select name='dest' class='am4-input rounded-md px-3 py-2 w-full max-w-xs' "
            "disabled><option value=''>Pick origin first</option></select>"
        )

    conn = get_read_conn()
    try:
        rows = fetch_all(
            conn,
            """
            SELECT DISTINCT ad.iata AS iata,
                   COALESCE(ad.name, '') AS name,
                   COALESCE(ad.country, '') AS country
            FROM route_aircraft ra
            JOIN airports ao ON ra.origin_id = ao.id
            JOIN airports ad ON ra.dest_id = ad.id
            WHERE ra.is_valid = 1 AND UPPER(ao.iata) = UPPER(?)
            AND ad.iata IS NOT NULL AND TRIM(ad.iata) != ''
            ORDER BY ad.iata
            """,
            [origin.strip()],
        )
    finally:
        conn.close()

    def _opt_label(d: dict) -> str:
        iata = d["iata"]
        nm = (d.get("name") or "").strip()
        co = (d.get("country") or "").strip()
        if nm and co:
            return f"{iata} — {nm} ({co})"
        if nm:
            return f"{iata} — {nm}"
        if co:
            return f"{iata} ({co})"
        return iata

    options = "".join(
        f'<option value="{html_escape(d["iata"])}">{html_escape(_opt_label(d))}</option>'
        for d in rows
    )
    return HTMLResponse(
        f"<select name='dest' class='am4-input rounded-md px-3 py-2 w-full max-w-xs' "
        f"hx-get='/api/route-compare' hx-trigger='change' "
        f"hx-target='#route-compare-table' hx-include='#route-analyzer-form' "
        f"hx-indicator='#route-spinner'><option value=''>Destination…</option>{options}</select>"
    )


@router.get("/route-compare", response_class=HTMLResponse)
def api_route_compare(
    request: Request,
    origin: str = Query(""),
    dest: str = Query(""),
    sort: str = Query("profit_per_ac_day"),
):
    if not origin.strip() or not dest.strip() or origin.strip().upper() == dest.strip().upper():
        return HTMLResponse("<p class='am4-text-secondary'>Choose origin and destination (different airports).</p>")

    sort_col = sort if sort in ROUTE_SORT else "profit_per_ac_day"
    order_sql = _route_order(sort_col)
    sql = f"""
        SELECT ac.shortname, ac.name, ac.type, ac.cost,
               ra.profit_per_ac_day, ra.trips_per_day, ra.profit_per_trip,
               ra.config_y, ra.config_j, ra.config_f,
               ra.ticket_y, ra.ticket_j, ra.ticket_f,
               ra.flight_time_hrs, ra.distance_km, ra.needs_stopover, ra.contribution
        FROM route_aircraft ra
        JOIN airports a0 ON ra.origin_id = a0.id
        JOIN airports a1 ON ra.dest_id = a1.id
        JOIN aircraft ac ON ra.aircraft_id = ac.id
        WHERE ra.is_valid = 1 AND UPPER(a0.iata) = UPPER(?) AND UPPER(a1.iata) = UPPER(?)
        ORDER BY {order_sql}
    """
    conn = get_read_conn()
    try:
        rows = fetch_all(conn, sql, [origin.strip(), dest.strip()])
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/route_compare_table.html",
        {"rows": rows, "sort": sort_col},
    )


@router.get("/route-chart", response_class=HTMLResponse)
def api_route_chart(request: Request, origin: str = Query(""), dest: str = Query("")):
    if not origin.strip() or not dest.strip():
        return HTMLResponse("")

    sql = """
        SELECT ac.shortname, ra.profit_per_ac_day
        FROM route_aircraft ra
        JOIN airports a0 ON ra.origin_id = a0.id
        JOIN airports a1 ON ra.dest_id = a1.id
        JOIN aircraft ac ON ra.aircraft_id = ac.id
        WHERE ra.is_valid = 1 AND UPPER(a0.iata) = UPPER(?) AND UPPER(a1.iata) = UPPER(?)
        ORDER BY ra.profit_per_ac_day DESC
    """
    conn = get_read_conn()
    try:
        data = fetch_all(conn, sql, [origin.strip(), dest.strip()])
    finally:
        conn.close()

    if not data:
        return HTMLResponse("<p class='am4-text-secondary text-sm'>No data for this pair.</p>")
    labels = [r["shortname"] for r in data]
    values = [float(r["profit_per_ac_day"] or 0) for r in data]

    return templates.TemplateResponse(
        request,
        "partials/chart_data.html",
        {
            "chart_id": "routeCompareChart",
            "labels": labels,
            "values": values,
            "label": "Profit/Day ($)",
        },
    )


def _hub_filter_sql(
    hub: str,
    atype: str,
    min_profit: float,
    max_dist: float,
    max_flight_hrs: float,
    hide_stop: bool,
) -> tuple[str, list]:
    query = "SELECT * FROM v_best_routes WHERE hub = ?"
    params: list = [hub]
    if atype:
        query += " AND UPPER(ac_type) = UPPER(?)"
        params.append(atype)
    query += " AND profit_per_ac_day >= ?"
    params.append(min_profit)
    if max_dist > 0:
        query += " AND distance_km <= ?"
        params.append(max_dist)
    if max_flight_hrs > 0:
        query += " AND flight_time_hrs <= ?"
        params.append(max_flight_hrs)
    if hide_stop:
        query += " AND needs_stopover = 0"
    return query, params


@router.get("/chart/profit-by-aircraft")
def chart_profit_by_aircraft(
    hub: str = Query(""),
    limit: int = Query(20, ge=5, le=100),
    filter_type: str = Query("", alias="type"),
) -> dict:
    if not hub.strip():
        return {"labels": [], "data": []}
    q, params = _hub_filter_sql(hub.strip(), filter_type.strip(), 0.0, 0.0, 0.0, False)
    q += " ORDER BY profit_per_ac_day DESC LIMIT ?"
    params.append(limit)
    conn = get_read_conn()
    try:
        rows = fetch_all(conn, q, params)
    finally:
        conn.close()
    labels = [f"{r['aircraft']}" for r in rows]
    data = [float(r["profit_per_ac_day"] or 0) for r in rows]
    return {"labels": labels, "data": data}


@router.get("/chart/profit-by-distance")
def chart_profit_by_distance(
    hub: str = Query(""),
    filter_type: str = Query("", alias="type"),
) -> dict:
    if not hub.strip():
        return {"labels": [], "data": []}
    q, params = _hub_filter_sql(hub.strip(), filter_type.strip(), 0.0, 0.0, 0.0, False)
    q += " ORDER BY distance_km ASC LIMIT 200"
    conn = get_read_conn()
    try:
        rows = fetch_all(conn, q, params)
    finally:
        conn.close()
    labels = [f"{int(r['distance_km'] or 0)} km" for r in rows]
    data = [float(r["profit_per_ac_day"] or 0) for r in rows]
    return {"labels": labels, "data": data}


@router.get("/chart/haul-breakdown")
def chart_haul_breakdown(
    hub: str = Query(""),
    filter_type: str = Query("", alias="type"),
) -> dict:
    if not hub.strip():
        return {"short": 0, "medium": 0, "long": 0}
    q, params = _hub_filter_sql(hub.strip(), filter_type.strip(), 0.0, 0.0, 0.0, False)
    conn = get_read_conn()
    try:
        rows = fetch_all(conn, q, params)
    finally:
        conn.close()
    short = medium = long_ = 0
    for r in rows:
        d = float(r["distance_km"] or 0)
        if d < 3000:
            short += 1
        elif d < 7000:
            medium += 1
        else:
            long_ += 1
    return {"short": short, "medium": medium, "long": long_}


@router.get("/aircraft-chart", response_class=HTMLResponse)
def api_aircraft_chart(
    request: Request,
    aircraft: str = Query(""),
    min_profit: float = Query(0.0),
    limit: int = Query(25, ge=5, le=100),
):
    if not aircraft.strip():
        return HTMLResponse("<p class='am4-text-secondary text-sm'>Select an aircraft.</p>")
    sql = """
        SELECT hub, AVG(profit_per_ac_day) AS avg_p
        FROM v_best_routes
        WHERE aircraft = ? AND profit_per_ac_day >= ?
        GROUP BY hub
        ORDER BY avg_p DESC
        LIMIT ?
    """
    conn = get_read_conn()
    try:
        rows = fetch_all(conn, sql, [aircraft.strip(), min_profit, limit])
    finally:
        conn.close()
    labels = [str(r["hub"]) for r in rows]
    values = [float(r["avg_p"] or 0) for r in rows]
    return templates.TemplateResponse(
        request,
        "partials/chart_data.html",
        {
            "chart_id": "aircraftHubChart",
            "labels": labels,
            "values": values,
            "label": "Avg profit/day by hub ($)",
        },
    )


_COST_BREAKDOWN_SORT = frozenset({"margin_pct", "fuel_pct", "name"})
_COST_TYPE_FILTER = frozenset({"PAX", "CARGO", "VIP"})


@router.get("/aircraft-cost-breakdown", response_class=HTMLResponse)
def api_aircraft_cost_breakdown(
    request: Request,
    sort: str = Query("margin_pct"),
    ac_type: str = Query(""),
):
    """Per-aircraft average cost stack as % of trip revenue (valid route rows only)."""
    sort_key = sort if sort in _COST_BREAKDOWN_SORT else "margin_pct"
    tf = ac_type.strip().upper()
    type_clause = ""
    params: list[str] = []
    if tf and tf in _COST_TYPE_FILTER:
        type_clause = " AND UPPER(TRIM(ac.type)) = ?"
        params.append(tf)

    sql = f"""
        SELECT ac.id, ac.shortname, ac.name, ac.type,
               AVG(ra.income) AS avg_income,
               AVG(ra.fuel_cost) AS avg_fuel,
               AVG(ra.co2_cost) AS avg_co2,
               AVG(ra.acheck_cost) AS avg_acheck,
               AVG(ra.repair_cost) AS avg_repair,
               AVG(ra.profit_per_trip) AS avg_profit,
               AVG(ra.income - ra.profit_per_trip - ra.fuel_cost - ra.co2_cost
                   - ra.acheck_cost - ra.repair_cost) AS avg_other
        FROM route_aircraft ra
        JOIN aircraft ac ON ra.aircraft_id = ac.id
        WHERE ra.is_valid = 1{type_clause}
        GROUP BY ac.id, ac.shortname, ac.name, ac.type
        HAVING AVG(ra.income) > 0
    """

    try:
        conn = get_read_conn()
    except FileNotFoundError:
        return HTMLResponse(
            HTML_DB_NOT_FOUND
        )

    try:
        rows = fetch_all(conn, sql, params)
    finally:
        conn.close()

    processed: list[dict] = []
    for r in rows:
        inc = float(r["avg_income"] or 0)
        if inc <= 0:
            continue
        fuel = float(r["avg_fuel"] or 0)
        co2 = float(r["avg_co2"] or 0)
        acheck = float(r["avg_acheck"] or 0)
        repair = float(r["avg_repair"] or 0)
        other = float(r["avg_other"] or 0)
        profit = float(r["avg_profit"] or 0)
        processed.append(
            {
                "shortname": str(r["shortname"] or ""),
                "name": str(r["name"] or ""),
                "type": str(r["type"] or ""),
                "fuel_pct": fuel / inc * 100.0,
                "co2_pct": co2 / inc * 100.0,
                "acheck_pct": acheck / inc * 100.0,
                "repair_pct": repair / inc * 100.0,
                "other_pct": other / inc * 100.0,
                "profit_pct": profit / inc * 100.0,
                "margin_pct": profit / inc * 100.0,
                "fuel_usd": fuel,
                "co2_usd": co2,
                "acheck_usd": acheck,
                "repair_usd": repair,
                "other_usd": other,
                "profit_usd": profit,
                "income_usd": inc,
            }
        )

    if sort_key == "name":
        processed.sort(key=lambda x: (x["shortname"] or "").upper())
    elif sort_key == "fuel_pct":
        processed.sort(key=lambda x: x["fuel_pct"], reverse=True)
    else:
        processed.sort(key=lambda x: x["margin_pct"], reverse=True)

    max_rows = 50
    processed = processed[:max_rows]

    if not processed:
        return HTMLResponse(
            "<p class='am4-text-secondary text-sm'>No valid route rows with positive average income.</p>"
        )

    labels = [p["shortname"] for p in processed]
    keys = ("fuel_pct", "co2_pct", "acheck_pct", "repair_pct", "other_pct", "profit_pct")
    dollar_keys = ("fuel_usd", "co2_usd", "acheck_usd", "repair_usd", "other_usd", "profit_usd")
    datasets_meta = [
        {"label": "Fuel", "pct_key": "fuel_pct", "dollar_key": "fuel_usd", "color": "#ef4444"},
        {"label": "CO₂", "pct_key": "co2_pct", "dollar_key": "co2_usd", "color": "#22c55e"},
        {"label": "A-check", "pct_key": "acheck_pct", "dollar_key": "acheck_usd", "color": "#3b82f6"},
        {"label": "Repair", "pct_key": "repair_pct", "dollar_key": "repair_usd", "color": "#a855f7"},
        {"label": "Other", "pct_key": "other_pct", "dollar_key": "other_usd", "color": "#6b7280"},
        {"label": "Profit", "pct_key": "profit_pct", "dollar_key": "profit_usd", "color": "#10b981"},
    ]
    datasets = [
        {
            "label": m["label"],
            "data": [float(p[m["pct_key"]]) for p in processed],
            "backgroundColor": m["color"],
            "dollarKey": m["dollar_key"],
        }
        for m in datasets_meta
    ]
    dollar_rows = []
    for p in processed:
        row = {dk: round(float(p[dk]), 2) for dk in dollar_keys}
        row["income_usd"] = round(float(p["income_usd"]), 2)
        dollar_rows.append(row)
    chart_height_px = max(280, len(labels) * 32)

    return templates.TemplateResponse(
        request,
        "partials/aircraft_cost_breakdown.html",
        {
            "chart_id": "aircraftCostBreakdownChart",
            "labels": labels,
            "datasets": datasets,
            "dollar_rows": dollar_rows,
            "chart_height_px": chart_height_px,
        },
    )
