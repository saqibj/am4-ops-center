"""HTMX fragments and JSON API under /api/* (per PRD)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from html import escape as html_escape

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from commands.fleet_recommend import fleet_recommend_rows
from config import UserConfig
from dashboard.db import DB_PATH, fetch_all, fetch_one, get_db
from dashboard.hub_freshness import STALE_AFTER_DAYS, hub_display_status
from dashboard.server import templates


def _stale_cutoff_iso(days: int = STALE_AFTER_DAYS) -> str:
    """ISO timestamp for 'now minus N days' in UTC, for SQL bound parameters."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


router = APIRouter(prefix="/api", tags=["api"])

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


@router.get("/search/airports", response_class=HTMLResponse)
def api_search_airports(
    request: Request,
    q: str = Query(""),
    hub_iata: str = Query(""),
    destination_iata: str = Query(""),
    field_id: str = Query("hub_iata"),
):
    term = _search_term_airports(q, hub_iata, destination_iata)
    if len(term) < 2:
        return HTMLResponse("")
    fid = _safe_field_id(field_id, "hub_iata")
    ut = term.upper()
    lt = term.lower()
    sql = """
        SELECT iata, icao, name, fullname, country
        FROM airports
        WHERE iata IS NOT NULL AND TRIM(iata) != ''
          AND (
            (iata IS NOT NULL AND INSTR(UPPER(iata), ?) > 0)
            OR (icao IS NOT NULL AND TRIM(icao) != '' AND INSTR(UPPER(icao), ?) > 0)
            OR INSTR(LOWER(COALESCE(name, '')), ?) > 0
            OR INSTR(LOWER(COALESCE(fullname, '')), ?) > 0
            OR INSTR(LOWER(COALESCE(country, '')), ?) > 0
          )
        ORDER BY iata COLLATE NOCASE
        LIMIT 25
    """
    conn = get_db()
    try:
        rows = fetch_all(conn, sql, [ut, ut, lt, lt, lt])
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "partials/search_airports_results.html",
        {"rows": rows, "field_id": fid},
    )


@router.get("/search/aircraft", response_class=HTMLResponse)
def api_search_aircraft(
    request: Request,
    q: str = Query(""),
    aircraft: str = Query(""),
    field_id: str = Query("aircraft_route"),
):
    term = (q or aircraft or "").strip()
    if len(term) < 1:
        return HTMLResponse("")
    fid = _safe_field_id(field_id, "aircraft_route")
    lt = term.lower()
    sql = """
        SELECT shortname, name, type, cost
        FROM aircraft
        WHERE INSTR(LOWER(shortname), ?) > 0
           OR INSTR(LOWER(COALESCE(name, '')), ?) > 0
           OR INSTR(LOWER(COALESCE(type, '')), ?) > 0
        ORDER BY shortname COLLATE NOCASE
        LIMIT 25
    """
    conn = get_db()
    try:
        rows = fetch_all(conn, sql, [lt, lt, lt])
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "partials/search_aircraft_results.html",
        {"rows": rows, "field_id": fid},
    )


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

    conn = get_db()
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

    q = """
        SELECT COUNT(*) AS n,
               AVG(profit_per_ac_day) AS avg_profit,
               MAX(profit_per_ac_day) AS best_profit
        FROM v_best_routes WHERE hub = ?
    """
    params: list = [hub.strip()]
    if atype:
        q += " AND UPPER(ac_type) = UPPER(?)"
        params.append(atype)
    q += " AND profit_per_ac_day >= ?"
    params.append(min_profit)
    if max_dist > 0:
        q += " AND distance_km <= ?"
        params.append(max_dist)
    if max_flight_hrs > 0:
        q += " AND flight_time_hrs <= ?"
        params.append(max_flight_hrs)
    if _truthy_stopover_hide(hide_stopovers):
        q += " AND needs_stopover = 0"

    conn = get_db()
    try:
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

    conn = get_db()
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
    conn = get_db()
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

    conn = get_db()
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

    conn = get_db()
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
    conn = get_db()
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
    conn = get_db()
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


def _query_flag_on(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "on", "yes")


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

    conn = get_db()
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

    conn = get_db()
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

    sql = """
        SELECT ap.iata AS iata, ap.name AS name, ap.lat AS lat, ap.lng AS lng,
               MAX(ra.profit_per_ac_day) AS profit_per_ac_day,
               GROUP_CONCAT(DISTINCT ac.shortname) AS aircraft_sample
        FROM route_aircraft ra
        JOIN airports orig ON ra.origin_id = orig.id
        JOIN airports ap ON ra.dest_id = ap.id
        JOIN aircraft ac ON ra.aircraft_id = ac.id
        WHERE ra.is_valid = 1 AND UPPER(orig.iata) = UPPER(?)
        AND ap.lat IS NOT NULL AND ap.lng IS NOT NULL
        GROUP BY ap.id
        ORDER BY profit_per_ac_day DESC
        LIMIT ?
    """
    conn = get_db()
    try:
        rows = fetch_all(conn, sql, [hub.strip(), top_n])
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
                "aircraft": r["aircraft_sample"] or "",
                "t": t,
            }
        )
    return out


@router.get("/heatmap-panel", response_class=HTMLResponse)
def api_heatmap_panel(request: Request, hub: str = Query(""), top_n: int = Query(100, ge=10, le=500)):
    """HTML+script panel driven by /api/heatmap-data JSON (same shape as inline markers)."""
    if not hub.strip():
        return HTMLResponse("<p class='am4-text-secondary p-4'>Select a hub.</p>")

    conn = get_db()
    try:
        rows = fetch_all(
            conn,
            """
            SELECT ap.iata AS iata, ap.name AS name, ap.lat AS lat, ap.lng AS lng,
                   MAX(ra.profit_per_ac_day) AS profit_per_ac_day,
                   GROUP_CONCAT(DISTINCT ac.shortname) AS aircraft_sample
            FROM route_aircraft ra
            JOIN airports orig ON ra.origin_id = orig.id
            JOIN airports ap ON ra.dest_id = ap.id
            JOIN aircraft ac ON ra.aircraft_id = ac.id
            WHERE ra.is_valid = 1 AND UPPER(orig.iata) = UPPER(?)
            AND ap.lat IS NOT NULL AND ap.lng IS NOT NULL
            GROUP BY ap.id
            ORDER BY profit_per_ac_day DESC
            LIMIT ?
            """,
            [hub.strip(), top_n],
        )
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
                "aircraft": r["aircraft_sample"] or "",
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


@router.get("/stats", response_class=HTMLResponse)
def api_stats(request: Request):
    try:
        conn = get_db()
        try:
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS routes,
                       COUNT(DISTINCT origin_id) AS hubs,
                       COUNT(DISTINCT aircraft_id) AS aircraft,
                       MAX(extracted_at) AS last_extract
                FROM route_aircraft WHERE is_valid = 1
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        row = {"routes": 0, "hubs": 0, "aircraft": 0, "last_extract": None}

    from pathlib import Path

    p = Path(DB_PATH)
    db_size = p.stat().st_size if p.exists() else None

    return templates.TemplateResponse(
        request,
        "partials/stats_cards.html",
        {"scope": "global", "stats": row, "db_size_bytes": db_size},
    )


@router.get("/hubs")
def api_hubs() -> list[dict]:
    try:
        conn = get_db()
        try:
            rows = fetch_all(
                conn,
                """
                SELECT DISTINCT a.iata AS iata, a.name AS name
                FROM route_aircraft ra
                JOIN airports a ON ra.origin_id = a.id
                WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
                ORDER BY a.iata
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        rows = []
    return rows


@router.get("/aircraft-list")
def api_aircraft_list() -> list[dict]:
    try:
        conn = get_db()
        try:
            rows = fetch_all(
                conn,
                "SELECT shortname, name, type, cost FROM aircraft ORDER BY shortname",
            )
        finally:
            conn.close()
    except FileNotFoundError:
        rows = []
    return rows


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
    conn = get_db()
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
    conn = get_db()
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
    conn = get_db()
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
    conn = get_db()
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


def _airline_est_profit_from_my_routes(conn) -> float:
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


def _my_fleet_rows(conn) -> list[dict]:
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


def _my_routes_rows(conn) -> list[dict]:
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


@router.get("/fleet/inventory", response_class=HTMLResponse)
def api_fleet_inventory(request: Request):
    try:
        conn = get_db()
        try:
            fleets = _my_fleet_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        fleets = []
    except sqlite3.OperationalError:
        fleets = []
    return templates.TemplateResponse(
        request,
        "partials/fleet_inventory.html",
        {"fleets": fleets},
    )


@router.get("/fleet/summary", response_class=HTMLResponse)
def api_fleet_summary(request: Request):
    try:
        conn = get_db()
        try:
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS types, COALESCE(SUM(mf.quantity), 0) AS planes
                FROM my_fleet mf
                """,
            )
            est = _airline_est_profit_from_my_routes(conn)
            rc = fetch_one(conn, "SELECT COUNT(*) AS c FROM my_routes")
            route_rows = int(rc["c"] or 0) if rc else 0
            val_row = fetch_one(
                conn,
                """
                SELECT COALESCE(SUM(mf.quantity * COALESCE(ac.cost, 0)), 0) AS fleet_value
                FROM my_fleet mf
                JOIN aircraft ac ON mf.aircraft_id = ac.id
                """,
            )
            ag_row = fetch_one(
                conn,
                """
                SELECT COALESCE(SUM(num_assigned), 0) AS assigned_total
                FROM my_routes
                """,
            )
            free_row = fetch_one(
                conn,
                """
                SELECT COALESCE(SUM(
                    CASE
                        WHEN mf.quantity > COALESCE(ra.asg, 0)
                        THEN mf.quantity - COALESCE(ra.asg, 0)
                        ELSE 0
                    END
                ), 0) AS free_total
                FROM my_fleet mf
                LEFT JOIN (
                    SELECT aircraft_id, SUM(num_assigned) AS asg
                    FROM my_routes
                    GROUP BY aircraft_id
                ) ra ON ra.aircraft_id = mf.aircraft_id
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        row = {"types": 0, "planes": 0}
        est = 0.0
        route_rows = 0
        val_row = {"fleet_value": 0}
        ag_row = {"assigned_total": 0}
        free_row = {"free_total": 0}
    except sqlite3.OperationalError:
        row = {"types": 0, "planes": 0}
        est = 0.0
        route_rows = 0
        val_row = {"fleet_value": 0}
        ag_row = {"assigned_total": 0}
        free_row = {"free_total": 0}
    stats = {
        "types": int(row["types"] or 0) if row else 0,
        "planes": int(row["planes"] or 0) if row else 0,
        "est_profit": est,
        "route_rows": route_rows,
        "fleet_value": float(val_row["fleet_value"] or 0) if val_row else 0.0,
        "assigned_total": int(ag_row["assigned_total"] or 0) if ag_row else 0,
        "free_total": int(free_row["free_total"] or 0) if free_row else 0,
    }
    return templates.TemplateResponse(
        request,
        "partials/fleet_summary.html",
        {"stats": stats},
    )


@router.post("/fleet/add", response_class=HTMLResponse)
def api_fleet_add(
    request: Request,
    aircraft: str = Form(""),
    quantity: int = Form(1),
    notes: str = Form(""),
):
    msg: str | None = None
    try:
        conn = get_db()
        try:
            ac = fetch_one(
                conn,
                "SELECT id FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
                [aircraft.strip()],
            )
            if not ac or not ac.get("id"):
                msg = "Unknown aircraft shortname."
            else:
                q = int(quantity) if quantity else 1
                q = max(1, min(999, q))
                prev = fetch_one(
                    conn,
                    "SELECT quantity FROM my_fleet WHERE aircraft_id = ?",
                    [int(ac["id"])],
                )
                conn.execute(
                    """
                    INSERT INTO my_fleet (aircraft_id, quantity, notes, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(aircraft_id) DO UPDATE SET
                        quantity = MIN(999, my_fleet.quantity + excluded.quantity),
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_fleet.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (int(ac["id"]), q, notes.strip() or None),
                )
                conn.commit()
                after = fetch_one(
                    conn,
                    "SELECT quantity FROM my_fleet WHERE aircraft_id = ?",
                    [int(ac["id"])],
                )
                if prev:
                    msg = f"Merged +{q} (now {int(after['quantity']) if after else q} owned for {aircraft.strip()})."
                else:
                    msg = f"Added {q} × {aircraft.strip()}."
        finally:
            conn.close()
    except FileNotFoundError:
        msg = "Database not found."
    except sqlite3.OperationalError:
        msg = "Database missing my_fleet table — run extract or upgrade schema."

    try:
        conn = get_db()
        try:
            fleets = _my_fleet_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        fleets = []

    ctx: dict = {"fleets": fleets}
    if msg and ("Database" in msg or "Unknown" in msg or "missing" in msg):
        ctx["flash_err"] = msg
    elif msg:
        ctx["flash"] = msg
    elif not ctx.get("flash_err"):
        ctx["flash"] = "Saved fleet row."
    return templates.TemplateResponse(request, "partials/fleet_inventory.html", ctx)


@router.post("/fleet/delete", response_class=HTMLResponse)
def api_fleet_delete(request: Request, fleet_id: int = Form(...)):
    try:
        conn = get_db()
        try:
            conn.execute("DELETE FROM my_fleet WHERE id = ?", (int(fleet_id),))
            conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        return templates.TemplateResponse(
            request,
            "partials/fleet_inventory.html",
            {"fleets": [], "flash_err": "Database not found."},
        )

    try:
        conn = get_db()
        try:
            fleets = _my_fleet_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        fleets = []
    return templates.TemplateResponse(
        request,
        "partials/fleet_inventory.html",
        {"fleets": fleets, "flash": "Removed aircraft type from fleet."},
    )


@router.post("/fleet/{fleet_id}/buy", response_class=HTMLResponse)
def api_fleet_buy(request: Request, fleet_id: int, add_count: int = Form(1)):
    flash: str | None = None
    flash_err: str | None = None
    try:
        conn = get_db()
        try:
            add = max(1, min(999, int(add_count) if add_count else 1))
            cur = conn.execute(
                """
                UPDATE my_fleet
                SET quantity = MIN(999, quantity + ?), updated_at = datetime('now')
                WHERE id = ?
                """,
                (add, int(fleet_id)),
            )
            if cur.rowcount == 0:
                flash_err = "Fleet row not found."
            else:
                row = fetch_one(
                    conn,
                    "SELECT quantity FROM my_fleet WHERE id = ?",
                    (int(fleet_id),),
                )
                new_q = int(row["quantity"]) if row else 0
                conn.commit()
                flash = f"Bought (now {new_q} owned)."
        finally:
            conn.close()
    except FileNotFoundError:
        flash_err = "Database not found."
    except sqlite3.OperationalError as exc:
        flash_err = str(exc)

    try:
        conn = get_db()
        try:
            fleets = _my_fleet_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        fleets = []
    ctx: dict = {"fleets": fleets}
    if flash_err:
        ctx["flash_err"] = flash_err
    elif flash:
        ctx["flash"] = flash
    return templates.TemplateResponse(request, "partials/fleet_inventory.html", ctx)


@router.post("/fleet/{fleet_id}/sell", response_class=HTMLResponse)
def api_fleet_sell(request: Request, fleet_id: int, sell_count: int = Form(1)):
    flash: str | None = None
    flash_err: str | None = None
    try:
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = fetch_one(
                conn,
                """
                SELECT mf.id, mf.quantity, mf.aircraft_id,
                       (SELECT COALESCE(SUM(num_assigned), 0)
                        FROM my_routes WHERE aircraft_id = mf.aircraft_id) AS assigned_sum
                FROM my_fleet mf
                WHERE mf.id = ?
                """,
                (int(fleet_id),),
            )
            if not row:
                conn.rollback()
                flash_err = "Fleet row not found."
            else:
                qty = int(row["quantity"] or 0)
                assigned = int(row["assigned_sum"] or 0)
                free = max(0, qty - assigned)
                want = max(1, int(sell_count) if sell_count else 1)
                sell_n = min(want, free)
                if free <= 0:
                    conn.rollback()
                    flash_err = "No unassigned aircraft to sell (reduce My Routes assignments first)."
                elif sell_n < want:
                    conn.rollback()
                    flash_err = f"Only {free} unassigned; cannot sell {want}."
                else:
                    new_q = qty - sell_n
                    if new_q <= 0:
                        conn.execute("DELETE FROM my_fleet WHERE id = ?", (int(fleet_id),))
                        flash = f"Sold all {qty}; removed type from fleet."
                    else:
                        conn.execute(
                            """
                            UPDATE my_fleet
                            SET quantity = ?, updated_at = datetime('now')
                            WHERE id = ?
                            """,
                            (new_q, int(fleet_id)),
                        )
                        flash = f"Sold {sell_n} (now {new_q} owned)."
                    conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        flash_err = "Database not found."
    except sqlite3.OperationalError as exc:
        flash_err = str(exc)

    try:
        conn = get_db()
        try:
            fleets = _my_fleet_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        fleets = []
    ctx: dict = {"fleets": fleets}
    if flash_err:
        ctx["flash_err"] = flash_err
    elif flash:
        ctx["flash"] = flash
    return templates.TemplateResponse(request, "partials/fleet_inventory.html", ctx)


@router.get("/fleet/json")
def api_fleet_json() -> list[dict]:
    try:
        conn = get_db()
        try:
            rows = _my_fleet_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        return []
    return [
        {
            "id": r["id"],
            "shortname": r["shortname"],
            "ac_name": r["ac_name"],
            "ac_type": r.get("ac_type"),
            "quantity": r["quantity"],
            "assigned": r.get("assigned", 0),
            "free": r.get("free", 0),
            "unit_cost": r.get("unit_cost", 0),
            "total_value": r.get("total_value", 0),
            "notes": r["notes"],
        }
        for r in rows
    ]


# --- My routes (my_routes table) ---


@router.get("/route-exists", response_class=HTMLResponse)
def api_route_exists(
    request: Request,
    origin: str = Query("", description="Hub IATA (alias for hub_iata)"),
    dest: str = Query("", description="Destination IATA (alias for destination_iata)"),
    aircraft: str = Query(""),
    hub_iata: str = Query(""),
    destination_iata: str = Query(""),
    num_assigned: int = Query(1, ge=1, le=999),
):
    h = (origin or hub_iata or "").strip()
    d = (dest or destination_iata or "").strip()
    ac = (aircraft or "").strip()
    incomplete = not h or not d or not ac
    if incomplete:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {"incomplete": True, "exists": False},
        )
    try:
        conn = get_db()
        try:
            hub = fetch_one(
                conn,
                "SELECT id, iata FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [h],
            )
            apd = fetch_one(
                conn,
                "SELECT id, iata FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [d],
            )
            acr = fetch_one(
                conn,
                "SELECT id, shortname FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
                [ac],
            )
            if not hub or not apd or not acr:
                return templates.TemplateResponse(
                    request,
                    "partials/route_exists_hint.html",
                    {
                        "incomplete": False,
                        "lookup_failed": True,
                        "exists": False,
                        "hub": h,
                        "dest": d,
                        "aircraft": ac,
                    },
                )
            row = fetch_one(
                conn,
                """
                SELECT num_assigned FROM my_routes
                WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                """,
                [int(hub["id"]), int(apd["id"]), int(acr["id"])],
            )
        finally:
            conn.close()
    except FileNotFoundError:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {"incomplete": True, "exists": False},
        )
    except sqlite3.OperationalError:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {"incomplete": True, "exists": False},
        )

    add_n = max(1, min(999, int(num_assigned or 1)))
    if not row:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {
                "incomplete": False,
                "exists": False,
                "hub": h,
                "dest": d,
                "aircraft": acr.get("shortname") or ac,
            },
        )
    cur = int(row["num_assigned"] or 0)
    return templates.TemplateResponse(
        request,
        "partials/route_exists_hint.html",
        {
            "incomplete": False,
            "exists": True,
            "hub": hub.get("iata") or h,
            "dest": apd.get("iata") or d,
            "aircraft": acr.get("shortname") or ac,
            "current": cur,
            "adding": add_n,
        },
    )


@router.get("/routes/pair-coverage", response_class=HTMLResponse)
def api_routes_pair_coverage(
    request: Request,
    hub_iata: str = Query(""),
    destination_iata: str = Query(""),
):
    hub = hub_iata.strip().upper()
    dest = destination_iata.strip().upper()
    my_rows: list[dict] = []
    extract_rows: list[dict] = []
    if not hub or not dest:
        return templates.TemplateResponse(
            request,
            "partials/route_pair_coverage.html",
            {"hub": hub, "dest": dest, "my_rows": [], "extract_rows": []},
        )
    try:
        conn = get_db()
        try:
            my_rows = fetch_all(
                conn,
                """
                SELECT ac.shortname AS aircraft, mr.num_assigned, mr.notes
                FROM my_routes mr
                JOIN airports ho ON mr.origin_id = ho.id
                JOIN airports hd ON mr.dest_id = hd.id
                JOIN aircraft ac ON mr.aircraft_id = ac.id
                WHERE UPPER(TRIM(ho.iata)) = UPPER(?) AND UPPER(TRIM(hd.iata)) = UPPER(?)
                ORDER BY ac.shortname COLLATE NOCASE
                """,
                [hub, dest],
            )
            extract_rows = fetch_all(
                conn,
                """
                SELECT ac.shortname, MAX(ra.profit_per_ac_day) AS profit_per_ac_day
                FROM route_aircraft ra
                JOIN airports a_orig ON ra.origin_id = a_orig.id
                JOIN airports a_dest ON ra.dest_id = a_dest.id
                JOIN aircraft ac ON ra.aircraft_id = ac.id
                WHERE ra.is_valid = 1
                  AND UPPER(TRIM(a_orig.iata)) = UPPER(?)
                  AND UPPER(TRIM(a_dest.iata)) = UPPER(?)
                GROUP BY ra.aircraft_id
                ORDER BY profit_per_ac_day DESC
                LIMIT 8
                """,
                [hub, dest],
            )
        finally:
            conn.close()
    except FileNotFoundError:
        pass
    except sqlite3.OperationalError:
        pass
    return templates.TemplateResponse(
        request,
        "partials/route_pair_coverage.html",
        {
            "hub": hub,
            "dest": dest,
            "my_rows": my_rows,
            "extract_rows": extract_rows,
        },
    )


@router.get("/routes/inventory", response_class=HTMLResponse)
def api_routes_inventory(request: Request):
    try:
        conn = get_db()
        try:
            routes = _my_routes_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        routes = []
    except sqlite3.OperationalError:
        routes = []
    return templates.TemplateResponse(
        request,
        "partials/my_routes_inventory.html",
        {"routes": routes},
    )


@router.get("/routes/summary", response_class=HTMLResponse)
def api_routes_summary(request: Request):
    try:
        conn = get_db()
        try:
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS nrows, COALESCE(SUM(num_assigned), 0) AS assigned
                FROM my_routes
                """,
            )
            est = _airline_est_profit_from_my_routes(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        row = {"nrows": 0, "assigned": 0}
        est = 0.0
    except sqlite3.OperationalError:
        row = {"nrows": 0, "assigned": 0}
        est = 0.0
    stats = {
        "nrows": int(row["nrows"] or 0) if row else 0,
        "assigned": int(row["assigned"] or 0) if row else 0,
        "est_profit": est,
    }
    return templates.TemplateResponse(
        request,
        "partials/my_routes_summary.html",
        {"stats": stats},
    )


@router.post("/routes/add", response_class=HTMLResponse)
def api_routes_add(
    request: Request,
    hub_iata: str = Form(""),
    destination_iata: str = Form(""),
    aircraft: str = Form(""),
    num_assigned: int = Form(1),
    notes: str = Form(""),
):
    msg: str | None = None
    try:
        conn = get_db()
        try:
            hub = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [hub_iata.strip()],
            )
            dest = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [destination_iata.strip()],
            )
            ac = fetch_one(
                conn,
                "SELECT id FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
                [aircraft.strip()],
            )
            if not hub:
                msg = "Unknown hub IATA."
            elif not dest:
                msg = "Unknown destination IATA."
            elif not ac:
                msg = "Unknown aircraft shortname."
            else:
                n = int(num_assigned) if num_assigned else 1
                n = max(1, min(999, n))
                prev = fetch_one(
                    conn,
                    """
                    SELECT num_assigned FROM my_routes
                    WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                    """,
                    [int(hub["id"]), int(dest["id"]), int(ac["id"])],
                )
                conn.execute(
                    """
                    INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                        num_assigned = MIN(999, my_routes.num_assigned + excluded.num_assigned),
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_routes.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (
                        int(hub["id"]),
                        int(dest["id"]),
                        int(ac["id"]),
                        n,
                        notes.strip() or None,
                    ),
                )
                conn.commit()
                after = fetch_one(
                    conn,
                    """
                    SELECT num_assigned FROM my_routes
                    WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                    """,
                    [int(hub["id"]), int(dest["id"]), int(ac["id"])],
                )
                if prev:
                    msg = (
                        f"Merged +{n} (now {int(after['num_assigned']) if after else n} assigned for "
                        f"{hub_iata.strip().upper()} → {destination_iata.strip().upper()} / {aircraft.strip()})."
                    )
                else:
                    msg = (
                        f"Added {n} × {aircraft.strip()} on "
                        f"{hub_iata.strip().upper()} → {destination_iata.strip().upper()}."
                    )
        finally:
            conn.close()
    except FileNotFoundError:
        msg = "Database not found."
    except sqlite3.OperationalError:
        msg = "Database missing my_routes table — run extract or upgrade schema."

    try:
        conn = get_db()
        try:
            routes = _my_routes_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        routes = []

    ctx: dict = {"routes": routes}
    if msg and ("Unknown" in msg or "Database" in msg or "missing" in msg):
        ctx["flash_err"] = msg
    elif msg:
        ctx["flash"] = msg
    elif not ctx.get("flash_err"):
        ctx["flash"] = "Saved route assignment."
    return templates.TemplateResponse(request, "partials/my_routes_inventory.html", ctx)


@router.post("/routes/delete", response_class=HTMLResponse)
def api_routes_delete(request: Request, my_route_id: int = Form(...)):
    try:
        conn = get_db()
        try:
            conn.execute("DELETE FROM my_routes WHERE id = ?", (int(my_route_id),))
            conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        return templates.TemplateResponse(
            request,
            "partials/my_routes_inventory.html",
            {"routes": [], "flash_err": "Database not found."},
        )

    try:
        conn = get_db()
        try:
            routes = _my_routes_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        routes = []
    return templates.TemplateResponse(
        request,
        "partials/my_routes_inventory.html",
        {"routes": routes, "flash": "Removed route row."},
    )


@router.get("/routes/json")
def api_routes_json() -> list[dict]:
    try:
        conn = get_db()
        try:
            rows = _my_routes_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        return []
    return [
        {
            "id": r["id"],
            "hub": r["hub"],
            "destination": r["destination"],
            "aircraft": r["aircraft"],
            "num_assigned": r["num_assigned"],
            "notes": r["notes"],
            "profit_per_ac_day": r["profit_per_ac_day"],
            "distance_km": r["distance_km"],
        }
        for r in rows
    ]


# --- Hub Manager (my_hubs) ---


def _dashboard_extract_config() -> UserConfig:
    """Load last saved extract UserConfig; merge my_fleet-derived plane count when present."""
    from database.schema import derived_total_planes, load_extract_config

    cfg = UserConfig()
    try:
        conn = get_db()
        try:
            loaded = load_extract_config(conn)
            if loaded is not None:
                cfg = loaded
            derived = derived_total_planes(conn)
            if derived is not None:
                cfg.total_planes_owned = derived
        finally:
            conn.close()
    except (FileNotFoundError, sqlite3.OperationalError):
        pass
    return cfg


_HUBS_AM4_UNAVAILABLE_MSG = (
    "The am4 package is not available in this Python environment. "
    "Hub add and refresh need am4 (see README): use Python 3.10–3.12, then "
    "pip install -r requirements.txt. On Windows without a working C++ build, use WSL."
)


def _am4_init() -> None:
    from am4.utils.db import init

    init()


def _hubs_ensure_schema(conn: sqlite3.Connection) -> None:
    from database.schema import create_schema

    create_schema(conn)


def _hub_inventory_rows(conn: sqlite3.Connection) -> list[dict]:
    return fetch_all(
        conn,
        """
        SELECT h.id, h.airport_id, h.iata, h.icao, h.name, h.fullname, h.country,
               h.notes, h.is_active, h.last_extracted_at, h.last_extract_status, h.last_extract_error,
               (SELECT COUNT(*) FROM route_aircraft ra
                WHERE ra.origin_id = h.airport_id AND ra.is_valid = 1) AS route_count,
               (SELECT MAX(ra.profit_per_ac_day) FROM route_aircraft ra
                WHERE ra.origin_id = h.airport_id AND ra.is_valid = 1) AS best_profit_day
        FROM v_my_hubs h
        ORDER BY h.iata COLLATE NOCASE
        """,
    )


def _hub_inventory_response(
    request: Request,
    *,
    flash: str | None = None,
    flash_err: str | None = None,
) -> HTMLResponse:
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            hubs = _hub_inventory_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        hubs = []
        flash_err = flash_err or "Database not found."
    except sqlite3.OperationalError as exc:
        hubs = []
        flash_err = flash_err or f"Database or view missing: {exc}"
    for h in hubs:
        h["display_status"] = hub_display_status(
            h.get("last_extract_status"), h.get("last_extracted_at")
        )
    ctx: dict = {"hubs": hubs, "stale_after_days": STALE_AFTER_DAYS}
    if flash:
        ctx["flash"] = flash
    if flash_err:
        ctx["flash_err"] = flash_err
    return templates.TemplateResponse(request, "partials/hub_inventory.html", ctx)


@router.get("/hubs/inventory", response_class=HTMLResponse)
def api_hubs_inventory(request: Request):
    return _hub_inventory_response(request)


@router.get("/hubs/summary", response_class=HTMLResponse)
def api_hubs_summary(request: Request):
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            cutoff = _stale_cutoff_iso()
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active,
                       SUM(CASE
                         WHEN last_extract_status = 'ok' AND NOT (
                           last_extracted_at IS NOT NULL
                           AND TRIM(last_extracted_at) != ''
                           AND datetime(last_extracted_at) IS NOT NULL
                           AND datetime(last_extracted_at) < datetime(?)
                         ) THEN 1 ELSE 0
                       END) AS fresh_ok,
                       SUM(CASE
                         WHEN last_extract_status = 'ok'
                          AND last_extracted_at IS NOT NULL
                          AND TRIM(last_extracted_at) != ''
                          AND datetime(last_extracted_at) IS NOT NULL
                          AND datetime(last_extracted_at) < datetime(?)
                         THEN 1 ELSE 0
                       END) AS stale_n,
                       SUM(CASE
                         WHEN last_extract_status = 'error' THEN 1
                         WHEN last_extract_status = 'running' THEN 1
                         WHEN last_extract_status IS NULL
                           OR TRIM(COALESCE(last_extract_status, '')) = '' THEN 1
                         WHEN last_extract_status NOT IN ('ok', 'error', 'running') THEN 1
                         ELSE 0
                       END) AS other_n
                FROM my_hubs
                """,
                [cutoff, cutoff],
            )
        finally:
            conn.close()
    except FileNotFoundError:
        row = {
            "total": 0,
            "active": 0,
            "fresh_ok": 0,
            "stale_n": 0,
            "other_n": 0,
        }
    except sqlite3.OperationalError:
        row = {
            "total": 0,
            "active": 0,
            "fresh_ok": 0,
            "stale_n": 0,
            "other_n": 0,
        }
    stats = {
        "total": int(row["total"] or 0) if row else 0,
        "active": int(row["active"] or 0) if row else 0,
        "fresh_ok": int(row["fresh_ok"] or 0) if row else 0,
        "stale_n": int(row["stale_n"] or 0) if row else 0,
        "other_n": int(row["other_n"] or 0) if row else 0,
        "stale_after_days": STALE_AFTER_DAYS,
    }
    return templates.TemplateResponse(request, "partials/hub_summary.html", {"stats": stats})


@router.post("/hubs/add", response_class=HTMLResponse)
def api_hubs_add(request: Request, iata_list: str = Form(""), notes: str = Form("")):
    parts = [p.strip().upper() for p in (iata_list or "").replace(";", ",").split(",") if p.strip()]
    if not parts:
        return _hub_inventory_response(request, flash_err="Enter at least one IATA code.")

    errs: list[str] = []
    n_ok = 0
    notes_val = notes.strip() or None
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            cfg = _dashboard_extract_config()
            _am4_init()
            from extractors.routes import upsert_airport_from_am4

            for iata in parts:
                ap_id, err = upsert_airport_from_am4(conn, cfg, iata)
                if err or ap_id is None:
                    errs.append(f"{iata}: {err or 'unknown error'}")
                    continue
                conn.execute(
                    """
                    INSERT INTO my_hubs (airport_id, notes, is_active, updated_at)
                    VALUES (?, ?, 1, datetime('now'))
                    ON CONFLICT(airport_id) DO UPDATE SET
                        is_active = 1,
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_hubs.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (ap_id, notes_val),
                )
                n_ok += 1
            conn.commit()
        finally:
            conn.close()
    except ImportError:
        return _hub_inventory_response(request, flash_err=_HUBS_AM4_UNAVAILABLE_MSG)
    except FileNotFoundError:
        return _hub_inventory_response(request, flash_err="Database not found.")
    except sqlite3.OperationalError as exc:
        return _hub_inventory_response(request, flash_err=str(exc))

    if n_ok == 0:
        return _hub_inventory_response(
            request,
            flash_err="\n".join(errs) if errs else "No hubs could be added.",
        )
    msg = f"Added or updated {n_ok} hub(s)."
    if errs:
        msg += "\n\n" + "\n".join(errs)
        return _hub_inventory_response(request, flash_err=msg)
    return _hub_inventory_response(request, flash=msg)


@router.post("/hubs/refresh", response_class=HTMLResponse)
def api_hubs_refresh(request: Request, hub_id: int = Form(...)):
    if not _try_acquire_extraction_lock():
        return _hub_inventory_response(request, flash_err=_EXTRACTION_BUSY_MSG)
    try:
        iata: str | None = None
        try:
            conn = get_db()
            try:
                _hubs_ensure_schema(conn)
                row = fetch_one(
                    conn,
                    "SELECT iata FROM v_my_hubs WHERE id = ? LIMIT 1",
                    [int(hub_id)],
                )
                if not row or not row.get("iata"):
                    return _hub_inventory_response(request, flash_err="Hub not found.")
                iata = str(row["iata"]).strip()
            finally:
                conn.close()
        except FileNotFoundError:
            return _hub_inventory_response(request, flash_err="Database not found.")

        try:
            _am4_init()
            from extractors.routes import refresh_single_hub

            refresh_single_hub(DB_PATH, _dashboard_extract_config(), iata)
        except ImportError:
            return _hub_inventory_response(request, flash_err=_HUBS_AM4_UNAVAILABLE_MSG)
        except RuntimeError as exc:
            return _hub_inventory_response(request, flash_err=str(exc))
        except ValueError as exc:
            return _hub_inventory_response(request, flash_err=str(exc))
        except Exception as exc:
            return _hub_inventory_response(request, flash_err=str(exc)[:800])

        return _hub_inventory_response(request, flash=f"Refreshed routes for {iata}.")
    finally:
        _release_extraction_lock()


@router.post("/hubs/refresh-stale", response_class=HTMLResponse)
def api_hubs_refresh_stale(request: Request):
    if not _try_acquire_extraction_lock():
        return _hub_inventory_response(request, flash_err=_EXTRACTION_BUSY_MSG)
    try:
        stale: list[dict] = []
        d = STALE_AFTER_DAYS
        cutoff = _stale_cutoff_iso()
        try:
            conn = get_db()
            try:
                _hubs_ensure_schema(conn)
                stale = fetch_all(
                    conn,
                    """
                    SELECT id, iata FROM v_my_hubs
                    WHERE last_extract_status = 'ok'
                      AND last_extracted_at IS NOT NULL
                      AND TRIM(last_extracted_at) != ''
                      AND datetime(last_extracted_at) IS NOT NULL
                      AND datetime(last_extracted_at) < datetime(?)
                    ORDER BY iata COLLATE NOCASE
                    """,
                    [cutoff],
                )
            finally:
                conn.close()
        except FileNotFoundError:
            return _hub_inventory_response(request, flash_err="Database not found.")
        except sqlite3.OperationalError as exc:
            return _hub_inventory_response(request, flash_err=str(exc))

        if not stale:
            return _hub_inventory_response(
                request,
                flash=f"No stale hubs (all OK extracts within {d} days, or use per-hub Refresh for errors).",
            )

        try:
            _am4_init()
            from extractors.routes import refresh_single_hub
        except ImportError:
            return _hub_inventory_response(request, flash_err=_HUBS_AM4_UNAVAILABLE_MSG)

        cfg = _dashboard_extract_config()
        errors: list[str] = []
        ok_n = 0
        for row in stale:
            code = (row.get("iata") or "").strip()
            if not code:
                continue
            try:
                refresh_single_hub(DB_PATH, cfg, code)
                ok_n += 1
            except (RuntimeError, ValueError) as exc:
                errors.append(f"{code}: {exc}")
            except Exception as exc:
                errors.append(f"{code}: {str(exc)[:200]}")

        msg = f"Refreshed {ok_n} stale hub(s) (extract older than {d} days)."
        if errors:
            msg += "\n" + "\n".join(errors)
            return _hub_inventory_response(request, flash_err=msg)
        return _hub_inventory_response(request, flash=msg)
    finally:
        _release_extraction_lock()


@router.post("/hubs/delete", response_class=HTMLResponse)
def api_hubs_delete(request: Request, hub_id: int = Form(...)):
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            conn.execute("DELETE FROM my_hubs WHERE id = ?", (int(hub_id),))
            conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        return _hub_inventory_response(request, flash_err="Database not found.")
    except sqlite3.OperationalError as exc:
        return _hub_inventory_response(request, flash_err=str(exc))

    return _hub_inventory_response(request, flash="Removed hub from manager.")
