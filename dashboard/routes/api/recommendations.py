"""Fleet plan, contributions, heatmap."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from commands.fleet_recommend import fleet_recommend_rows
from dashboard.db import fetch_all, fetch_one, get_db
from dashboard.server import templates

from dashboard.routes.api.shared import CONTRIB_SORT, _contrib_order, _query_flag_on

router = APIRouter()


def _parse_buy_next_budget(budget: str | None) -> int | None:
    if budget is None or str(budget).strip() == "":
        return None
    try:
        return max(0, int(float(budget)))
    except ValueError:
        return None


def _buy_next_ac_type_filter(ac_type: str) -> str | None:
    m = {"pax": "PAX", "cargo": "CARGO", "vip": "VIP"}
    return m.get((ac_type or "").strip().lower())


def _exclude_owned_from_request(request: Request) -> bool:
    vals = request.query_params.getlist("exclude_owned")
    if not vals:
        return True
    return "1" in vals


def _buy_next_phase_a(
    conn,
    *,
    origin_id: int | None,
    budget_val: int | None,
    type_filter: str | None,
    exclude_owned: bool,
    top_n: int,
) -> list[dict]:
    sql = """
    SELECT ac.id AS aircraft_id,
           ac.shortname, ac.name, ac.type, ac.cost, ac.capacity, ac.range_km,
           COUNT(*) AS route_count,
           AVG(ra.profit_per_ac_day) AS avg_daily_profit,
           MAX(ra.profit_per_ac_day) AS best_daily_profit
    FROM route_aircraft ra
    JOIN aircraft ac ON ra.aircraft_id = ac.id
    WHERE ra.is_valid = 1
    """
    params: list = []
    if origin_id is not None:
        sql += " AND ra.origin_id = ?"
        params.append(origin_id)
    if budget_val is not None:
        sql += " AND ac.cost <= ?"
        params.append(budget_val)
    if type_filter:
        sql += " AND UPPER(TRIM(ac.type)) = UPPER(TRIM(?))"
        params.append(type_filter)
    if exclude_owned:
        sql += """
        AND NOT EXISTS (
            SELECT 1 FROM my_fleet mf
            WHERE mf.aircraft_id = ac.id AND COALESCE(mf.quantity, 0) > 0
        )
        """
    sql += """
    GROUP BY ac.id, ac.shortname, ac.name, ac.type, ac.cost, ac.capacity, ac.range_km
    HAVING AVG(ra.profit_per_ac_day) > 0
    ORDER BY (ac.cost * 1.0 / AVG(ra.profit_per_ac_day)) ASC
    LIMIT ?
    """
    params.append(top_n)
    return fetch_all(conn, sql, params)


def _allocation_hub_iatas(conn) -> list[str]:
    """Hubs the user operates (My Routes origins); else any extracted origin IATA."""
    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT a.iata AS iata
        FROM my_routes mr
        JOIN airports a ON mr.origin_id = a.id
        WHERE a.iata IS NOT NULL AND TRIM(a.iata) != ''
        ORDER BY a.iata
        """,
    )
    out = [str(r["iata"]).strip() for r in rows if r.get("iata")]
    if out:
        return out
    rows = fetch_all(
        conn,
        """
        SELECT DISTINCT a.iata AS iata
        FROM route_aircraft ra
        JOIN airports a ON ra.origin_id = a.id
        WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
        ORDER BY a.iata
        """,
    )
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
        return [], ["No hub scope: add My Routes or run an extract with origins."]

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
    ac_type: str = Query(""),
    top_n: int = Query(5, ge=1, le=20),
):
    budget_val = _parse_buy_next_budget(budget)
    exclude_owned = _exclude_owned_from_request(request)
    type_filter = _buy_next_ac_type_filter(ac_type)

    try:
        conn = get_db()
    except FileNotFoundError:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found. Configure AM4_ROUTEMINE_DB or run an extract.</p>"
        )

    try:
        origin_id: int | None = None
        if hub.strip():
            hub_row = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [hub.strip()],
            )
            if not hub_row:
                return HTMLResponse("<p class='text-amber-400'>Unknown hub.</p>")
            origin_id = int(hub_row["id"])

        candidates = _buy_next_phase_a(
            conn,
            origin_id=origin_id,
            budget_val=budget_val,
            type_filter=type_filter,
            exclude_owned=exclude_owned,
            top_n=top_n,
        )

        allocation_hubs = _allocation_hub_iatas(conn)

        recommendations: list[dict] = []
        for row in candidates:
            avg = float(row["avg_daily_profit"] or 0)
            cost = int(row["cost"] or 0)
            payback_days = round(cost / avg, 1) if avg > 0 else 0.0
            aid = int(row["aircraft_id"])
            top_routes = _buy_next_top_routes(conn, aid, origin_id)
            recommendations.append(
                {
                    "aircraft_id": aid,
                    "shortname": row["shortname"],
                    "name": row["name"],
                    "type": row["type"],
                    "cost": cost,
                    "capacity": row["capacity"],
                    "range_km": row["range_km"],
                    "route_count": int(row["route_count"] or 0),
                    "avg_daily_profit": avg,
                    "best_daily_profit": float(row["best_daily_profit"] or 0),
                    "payback_days": payback_days,
                    "top_routes": top_routes,
                }
            )

        return templates.TemplateResponse(
            request,
            "partials/buy_next_results.html",
            {
                "recommendations": recommendations,
                "allocation_hubs": allocation_hubs,
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
        conn = get_db()
    except FileNotFoundError:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found. Configure AM4_ROUTEMINE_DB or run an extract.</p>"
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
