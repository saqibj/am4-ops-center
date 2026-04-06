"""Demand utilization: My Routes vs route_demands (Y/J/F seats offered vs demand)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.db import fetch_all, get_db
from dashboard.server import templates

router = APIRouter()

_DEMAND_UTIL_SQL = """
SELECT ho.iata AS hub,
       hd.iata AS dest,
       ac.shortname AS ac,
       UPPER(TRIM(COALESCE(ac.type, ''))) AS ac_type,
       COALESCE(ra.config_y, 0) AS config_y,
       COALESCE(ra.config_j, 0) AS config_j,
       COALESCE(ra.config_f, 0) AS config_f,
       COALESCE(ra.trips_per_day, 0) AS trips_per_day,
       COALESCE(mr.num_assigned, 0) AS num_assigned,
       COALESCE(rd.demand_y, 0) AS demand_y,
       COALESCE(rd.demand_j, 0) AS demand_j,
       COALESCE(rd.demand_f, 0) AS demand_f
FROM my_routes mr
JOIN route_aircraft ra
     ON ra.origin_id = mr.origin_id
    AND ra.dest_id = mr.dest_id
    AND ra.aircraft_id = mr.aircraft_id
    AND ra.is_valid = 1
JOIN route_demands rd
     ON rd.origin_id = mr.origin_id
    AND rd.dest_id = mr.dest_id
JOIN aircraft ac ON mr.aircraft_id = ac.id
JOIN airports ho ON mr.origin_id = ho.id
JOIN airports hd ON mr.dest_id = hd.id
ORDER BY ho.iata, hd.iata, ac.shortname
"""

_CLASSIFICATIONS = frozenset({"underserved", "saturated", "wasted"})
_AC_TYPES = frozenset({"PAX", "CARGO", "VIP"})


def _cabin_class_and_unmet(demand: int, offered: int) -> tuple[int, str]:
    """Return (unmet, class) where unmet = demand - offered."""
    d = max(int(demand), 0)
    o = max(int(offered), 0)
    unmet = d - o
    if d <= 0:
        if o > 0:
            return unmet, "wasted"
        return 0, "saturated"
    if unmet > 0:
        return unmet, "underserved"
    if unmet < -0.1 * d:
        return unmet, "wasted"
    return unmet, "saturated"


def _enrich_row(r: dict) -> dict:
    trips = int(r["trips_per_day"] or 0)
    n = int(r["num_assigned"] or 0)
    cy, cj, cf = int(r["config_y"] or 0), int(r["config_j"] or 0), int(r["config_f"] or 0)
    dy, dj, df = int(r["demand_y"] or 0), int(r["demand_j"] or 0), int(r["demand_f"] or 0)

    oy = cy * trips * n
    oj = cj * trips * n
    of = cf * trips * n

    uy, y_cls = _cabin_class_and_unmet(dy, oy)
    uj, j_cls = _cabin_class_and_unmet(dj, oj)
    uf, f_cls = _cabin_class_and_unmet(df, of)

    def _bar(d: int, o: int) -> tuple[float, float]:
        m = max(int(d), int(o), 1)
        return 100.0 * int(d) / m, 100.0 * int(o) / m

    ypd, ypo = _bar(dy, oy)
    jpd, jpo = _bar(dj, oj)
    fpd, fpo = _bar(df, of)

    out = dict(r)
    out.update(
        {
            "y_offered": oy,
            "j_offered": oj,
            "f_offered": of,
            "y_unmet": uy,
            "j_unmet": uj,
            "f_unmet": uf,
            "y_class": y_cls,
            "j_class": j_cls,
            "f_class": f_cls,
            "y_pct_dem": ypd,
            "y_pct_off": ypo,
            "j_pct_dem": jpd,
            "j_pct_off": jpo,
            "f_pct_dem": fpd,
            "f_pct_off": fpo,
        }
    )
    return out


def _row_matches_classification(row: dict, clf: str) -> bool:
    if clf == "all" or not clf:
        return True
    if clf not in _CLASSIFICATIONS:
        return True
    for k in ("y_class", "j_class", "f_class"):
        if row.get(k) == clf:
            return True
    return False


def _apply_filters(
    rows: list[dict],
    hub: str,
    ac_type: str,
    classification: str,
) -> list[dict]:
    h = hub.strip().upper()
    at = ac_type.strip().upper()
    clf = classification.strip().lower() if classification else "all"

    out: list[dict] = []
    for r in rows:
        if h and str(r.get("hub") or "").strip().upper() != h:
            continue
        if at and at in _AC_TYPES:
            if str(r.get("ac_type") or "").strip().upper() != at:
                continue
        if not _row_matches_classification(r, clf):
            continue
        out.append(r)
    return out


@router.get("/demand-utilization", response_class=HTMLResponse)
def api_demand_utilization(
    request: Request,
    hub: str = Query(""),
    ac_type: str = Query("", alias="type"),
    classification: str = Query("all"),
):
    try:
        conn = get_db()
    except FileNotFoundError:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found. Configure AM4_ROUTEMINE_DB or run an extract.</p>"
        )

    try:
        raw = fetch_all(conn, _DEMAND_UTIL_SQL)
    finally:
        conn.close()

    rows = [_enrich_row(dict(r)) for r in raw]
    clf = classification.strip().lower() if classification else "all"
    if clf not in ("all",) + tuple(_CLASSIFICATIONS):
        clf = "all"
    filtered = _apply_filters(rows, hub, ac_type, clf)

    return templates.TemplateResponse(
        request,
        "partials/demand_utilization_results.html",
        {"rows": filtered, "total_before_filter": len(rows)},
    )
