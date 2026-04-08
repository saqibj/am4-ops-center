"""Fleet Health: gap between assigned aircraft and best alternative per route."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.db import fetch_all, get_read_db
from dashboard.server import templates

router = APIRouter()

_FLEET_HEALTH_SQL = """
SELECT mr.id AS my_route_id,
       mr.origin_id, mr.dest_id, mr.aircraft_id AS my_ac_id,
       mr.num_assigned,
       COALESCE(ra_mine.profit_per_ac_day, 0) AS my_profit_day,
       ra_mine.config_y AS my_y, ra_mine.config_j AS my_j, ra_mine.config_f AS my_f,
       ho.iata AS hub, hd.iata AS dest,
       ac_mine.shortname AS my_ac,
       ac_best.shortname AS best_ac,
       best_ra.aircraft_id AS best_ac_id,
       COALESCE(best_ra.profit_per_ac_day, 0) AS best_profit_day,
       best_ra.config_y AS best_y, best_ra.config_j AS best_j, best_ra.config_f AS best_f,
       (COALESCE(best_ra.profit_per_ac_day, 0)
        - COALESCE(ra_mine.profit_per_ac_day, 0)) AS daily_gap_per_ac,
       (COALESCE(best_ra.profit_per_ac_day, 0)
        - COALESCE(ra_mine.profit_per_ac_day, 0)) * mr.num_assigned AS daily_gap_total,
       CASE
           WHEN mr.aircraft_id = best_ra.aircraft_id
                AND (
                    COALESCE(ra_mine.config_y, -1) != COALESCE(best_ra.config_y, -1)
                    OR COALESCE(ra_mine.config_j, -1) != COALESCE(best_ra.config_j, -1)
                    OR COALESCE(ra_mine.config_f, -1) != COALESCE(best_ra.config_f, -1)
                )
           THEN 1
           ELSE 0
       END AS reconfig_only
FROM my_routes mr
JOIN route_aircraft ra_mine
     ON ra_mine.origin_id = mr.origin_id
    AND ra_mine.dest_id   = mr.dest_id
    AND ra_mine.aircraft_id = mr.aircraft_id
    AND ra_mine.is_valid  = 1
JOIN airports ho ON mr.origin_id = ho.id
JOIN airports hd ON mr.dest_id   = hd.id
JOIN aircraft ac_mine ON mr.aircraft_id = ac_mine.id
LEFT JOIN route_aircraft best_ra
     ON best_ra.id = (
         SELECT ra2.id FROM route_aircraft ra2
         WHERE ra2.origin_id = mr.origin_id
           AND ra2.dest_id   = mr.dest_id
           AND ra2.is_valid  = 1
         ORDER BY ra2.profit_per_ac_day DESC
         LIMIT 1
     )
LEFT JOIN aircraft ac_best ON best_ra.aircraft_id = ac_best.id
ORDER BY daily_gap_total DESC
"""


def _row_is_optimal(r: dict) -> bool:
    """Same aircraft and same Y/J/F as the best row — no swap or reconfig opportunity."""
    if int(r["my_ac_id"]) != int(r["best_ac_id"]):
        return False
    return (
        (r.get("my_y") or 0) == (r.get("best_y") or 0)
        and (r.get("my_j") or 0) == (r.get("best_j") or 0)
        and (r.get("my_f") or 0) == (r.get("best_f") or 0)
    )


def _hide_optimal_from_request(request: Request) -> bool:
    """Default: hide rows already flying the best aircraft with the best config."""
    vals = request.query_params.getlist("hide_optimal")
    if not vals:
        return True
    return "1" in vals


def _reconfig_only_from_request(request: Request) -> bool:
    vals = request.query_params.getlist("reconfig_only")
    if not vals:
        return False
    return "1" in vals


def _apply_filters(
    rows: list[dict],
    *,
    hub: str,
    min_gap: float,
    hide_optimal: bool,
    reconfig_only: bool,
) -> list[dict]:
    out: list[dict] = []
    hub_u = (hub or "").strip().upper()
    for r in rows:
        if hub_u and (r.get("hub") or "").strip().upper() != hub_u:
            continue
        gap_total = float(r.get("daily_gap_total") or 0)
        if gap_total < min_gap:
            continue
        if hide_optimal and _row_is_optimal(r):
            continue
        if reconfig_only and not int(r.get("reconfig_only") or 0):
            continue
        out.append(r)
    return out


@router.get("/fleet-health", response_class=HTMLResponse)
def api_fleet_health(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    hub: str = Query(""),
    min_gap: float = Query(0.0, ge=0.0),
):
    hide_optimal = _hide_optimal_from_request(request)
    reconfig_only = _reconfig_only_from_request(request)

    if conn is None:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found. Configure AM4_ROUTEMINE_DB or run an extract.</p>"
        )

    raw = fetch_all(conn, _FLEET_HEALTH_SQL)

    filtered = _apply_filters(
        raw,
        hub=hub,
        min_gap=min_gap,
        hide_optimal=hide_optimal,
        reconfig_only=reconfig_only,
    )
    summary_left = sum(float(r.get("daily_gap_total") or 0) for r in filtered)

    return templates.TemplateResponse(
        request,
        "partials/fleet_health_table.html",
        {
            "rows": filtered,
            "summary_left": summary_left,
        },
    )
