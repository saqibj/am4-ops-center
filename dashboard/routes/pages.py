"""Full HTML pages (PRD paths)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from dashboard.db import base_context, fetch_all, get_db
from dashboard.server import templates

router = APIRouter(tags=["pages"])


def _hubs_with_names() -> list[dict]:
    try:
        conn = get_db()
        try:
            return fetch_all(
                conn,
                """
                SELECT DISTINCT a.iata AS iata, COALESCE(a.name, '') AS name
                FROM route_aircraft ra
                JOIN airports a ON ra.origin_id = a.id
                WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
                ORDER BY a.iata
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        return []


@router.get("/", response_class=HTMLResponse)
def page_index(request: Request):
    from dashboard.db import db_file_size_bytes, fetch_one

    try:
        conn = get_db()
        try:
            stats = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS routes,
                       COUNT(DISTINCT origin_id) AS hubs,
                       COUNT(DISTINCT aircraft_id) AS aircraft,
                       MAX(extracted_at) AS last_extract
                FROM route_aircraft WHERE is_valid = 1
                """,
            )
            top_routes = fetch_all(
                conn,
                """
                SELECT a_orig.iata AS hub, a_dest.iata AS destination, ac.shortname AS aircraft,
                       ra.profit_per_ac_day
                FROM route_aircraft ra
                JOIN airports a_orig ON ra.origin_id = a_orig.id
                JOIN airports a_dest ON ra.dest_id = a_dest.id
                JOIN aircraft ac ON ra.aircraft_id = ac.id
                WHERE ra.is_valid = 1
                ORDER BY ra.profit_per_ac_day DESC
                LIMIT 10
                """,
            )
            top_hubs = fetch_all(
                conn,
                """
                SELECT a.iata AS hub, AVG(ra.profit_per_ac_day) AS avg_profit
                FROM route_aircraft ra
                JOIN airports a ON ra.origin_id = a.id
                WHERE ra.is_valid = 1
                GROUP BY ra.origin_id
                ORDER BY avg_profit DESC
                LIMIT 5
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        stats = {"routes": 0, "hubs": 0, "aircraft": 0, "last_extract": None}
        top_routes = []
        top_hubs = []

    ctx = base_context(request)
    ctx.update(
        {
            "stats": stats,
            "top_routes": top_routes,
            "hub_chart_labels": [str(h["hub"]) for h in top_hubs],
            "hub_chart_values": [round(float(h["avg_profit"] or 0), 2) for h in top_hubs],
            "db_size_bytes": db_file_size_bytes(),
        }
    )
    return templates.TemplateResponse(request, "index.html", ctx)


@router.get("/hub-explorer", response_class=HTMLResponse)
def page_hub_explorer(request: Request):
    ctx = base_context(request)
    ctx.update({"hubs": _hubs_with_names()})
    return templates.TemplateResponse(request, "hub_explorer.html", ctx)


@router.get("/aircraft", response_class=HTMLResponse)
def page_aircraft(request: Request):
    try:
        conn = get_db()
        try:
            aircraft = fetch_all(
                conn,
                "SELECT shortname, name, type, cost FROM aircraft ORDER BY shortname",
            )
        finally:
            conn.close()
    except FileNotFoundError:
        aircraft = []
    ctx = base_context(request)
    ctx.update({"aircraft": aircraft})
    return templates.TemplateResponse(request, "aircraft.html", ctx)


@router.get("/route-analyzer", response_class=HTMLResponse)
def page_route_analyzer(request: Request):
    try:
        conn = get_db()
        try:
            origins = fetch_all(
                conn,
                """
                SELECT DISTINCT a.iata AS iata,
                       COALESCE(a.name, '') AS name,
                       COALESCE(a.country, '') AS country
                FROM route_aircraft ra
                JOIN airports a ON ra.origin_id = a.id
                WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
                ORDER BY a.iata
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        origins = []
    ctx = base_context(request)
    ctx.update({"origins": origins})
    return templates.TemplateResponse(request, "route_analyzer.html", ctx)


@router.get("/fleet-planner", response_class=HTMLResponse)
def page_fleet_planner(request: Request):
    try:
        conn = get_db()
        try:
            hubs = fetch_all(
                conn,
                """
                SELECT DISTINCT a.iata AS iata FROM route_aircraft ra
                JOIN airports a ON ra.origin_id = a.id
                WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
                ORDER BY a.iata
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        hubs = []
    ctx = base_context(request)
    ctx.update({"hubs": [h["iata"] for h in hubs]})
    return templates.TemplateResponse(request, "fleet_planner.html", ctx)


@router.get("/my-fleet", response_class=HTMLResponse)
def page_my_fleet(request: Request):
    try:
        conn = get_db()
        try:
            aircraft = fetch_all(
                conn,
                "SELECT shortname, name FROM aircraft ORDER BY shortname",
            )
        finally:
            conn.close()
    except FileNotFoundError:
        aircraft = []
    ctx = base_context(request)
    ctx.update({"aircraft": aircraft})
    return templates.TemplateResponse(request, "my_fleet.html", ctx)


def _airports_with_iata() -> list[dict]:
    try:
        conn = get_db()
        try:
            return fetch_all(
                conn,
                """
                SELECT iata, COALESCE(name, '') AS name
                FROM airports
                WHERE iata IS NOT NULL AND TRIM(iata) != ''
                ORDER BY iata COLLATE NOCASE
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        return []


@router.get("/my-hubs", response_class=HTMLResponse)
def page_my_hubs(request: Request):
    ctx = base_context(request)
    return templates.TemplateResponse(request, "my_hubs.html", ctx)


@router.get("/my-routes", response_class=HTMLResponse)
def page_my_routes(request: Request):
    try:
        conn = get_db()
        try:
            aircraft = fetch_all(
                conn,
                "SELECT shortname, name FROM aircraft ORDER BY shortname",
            )
        finally:
            conn.close()
    except FileNotFoundError:
        aircraft = []
    ctx = base_context(request)
    ctx.update({"airports": _airports_with_iata(), "aircraft": aircraft})
    return templates.TemplateResponse(request, "my_routes.html", ctx)


@router.get("/contributions", response_class=HTMLResponse)
def page_contributions(request: Request):
    try:
        conn = get_db()
        try:
            hubs = fetch_all(conn, "SELECT DISTINCT hub FROM v_best_routes ORDER BY hub")
        finally:
            conn.close()
    except FileNotFoundError:
        hubs = []
    ctx = base_context(request)
    ctx.update({"hubs": [h["hub"] for h in hubs]})
    return templates.TemplateResponse(request, "contributions.html", ctx)


@router.get("/heatmap", response_class=HTMLResponse)
def page_heatmap(request: Request):
    hl = _hubs_with_names()
    default_hub = hl[0]["iata"] if hl else ""
    ctx = base_context(request)
    ctx.update({"hubs": hl, "default_hub": default_hub})
    return templates.TemplateResponse(request, "heatmap.html", ctx)
