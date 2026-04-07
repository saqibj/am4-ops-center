"""Full HTML pages (PRD paths)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config import UserConfig
from dashboard.db import base_context, fetch_all, fetch_one, get_db
from database.extraction_runs import list_completed_runs
from database.schema import load_extract_config
from dashboard.hub_freshness import STALE_AFTER_DAYS
from dashboard.routes.api.saved_filters import FORM_IDS as SAVED_FILTER_FORM_IDS
from dashboard.server import templates
from dashboard.ui_settings import ALLOWED_LANDING_PATHS
from database.saved_filters import list_saved_filters

router = APIRouter(tags=["pages"])


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("am4-routemine")
    except Exception:
        return "0.1.1"


def _origin_hub_iatas_for_fleet_plan() -> list[str]:
    """Distinct origin IATA codes present in extracted route_aircraft (valid rows)."""
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
        return []
    return [h["iata"] for h in hubs]


def _saved_filters_bar_context(page_key: str) -> dict:
    """Context keys for partials/saved_filters_bar.html."""
    items: list = []
    try:
        conn = get_db()
        try:
            items = list_saved_filters(conn, page_key)
        finally:
            conn.close()
    except FileNotFoundError:
        pass
    return {
        "saved_filter_page": page_key,
        "saved_filter_form_id": SAVED_FILTER_FORM_IDS[page_key],
        "saved_filter_items": items,
        "saved_filter_error": None,
    }


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
    ctx = base_context(request)
    ctx.update({"hubs": _origin_hub_iatas_for_fleet_plan()})
    ctx.update(_saved_filters_bar_context("fleet-planner"))
    return templates.TemplateResponse(request, "fleet_planner.html", ctx)


@router.get("/buy-next", response_class=HTMLResponse)
def page_buy_next(request: Request):
    ctx = base_context(request)
    ctx.update({"hubs": _origin_hub_iatas_for_fleet_plan()})
    ctx.update(_saved_filters_bar_context("buy-next"))
    return templates.TemplateResponse(request, "buy_next.html", ctx)


@router.get("/buy-next/global", response_class=HTMLResponse)
def page_buy_next_global(request: Request):
    ctx = base_context(request)
    ctx.update(_saved_filters_bar_context("buy-next-global"))
    return templates.TemplateResponse(request, "buy_next_global.html", ctx)


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
    ctx["stale_after_days"] = STALE_AFTER_DAYS
    return templates.TemplateResponse(request, "my_hubs.html", ctx)


def _hub_iatas_from_my_routes() -> list[str]:
    try:
        conn = get_db()
        try:
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
        finally:
            conn.close()
    except FileNotFoundError:
        return []
    return [r["iata"] for r in rows]


@router.get("/fleet-health", response_class=HTMLResponse)
def page_fleet_health(request: Request):
    ctx = base_context(request)
    ctx.update({"hubs": _hub_iatas_from_my_routes()})
    ctx.update(_saved_filters_bar_context("fleet-health"))
    return templates.TemplateResponse(request, "fleet_health.html", ctx)


@router.get("/demand-utilization", response_class=HTMLResponse)
def page_demand_utilization(request: Request):
    ctx = base_context(request)
    ctx.update({"hubs": _hub_iatas_from_my_routes()})
    ctx.update(_saved_filters_bar_context("demand-utilization"))
    return templates.TemplateResponse(request, "demand_utilization.html", ctx)


@router.get("/extraction-deltas", response_class=HTMLResponse)
def page_extraction_deltas(request: Request):
    ctx = base_context(request)
    ctx.update({"hubs": _hub_iatas_from_my_routes()})
    try:
        conn = get_db()
        try:
            ctx["extraction_runs"] = list_completed_runs(conn, limit=100)
        finally:
            conn.close()
    except FileNotFoundError:
        ctx["extraction_runs"] = []
    ctx.update(_saved_filters_bar_context("extraction-deltas"))
    return templates.TemplateResponse(request, "extraction_deltas.html", ctx)


_HUB_ROI_SQL = """
SELECT ho.iata AS hub,
       COUNT(DISTINCT mr.id) AS routes,
       SUM(mr.num_assigned) AS aircraft_deployed,
       SUM(ac.cost * mr.num_assigned) AS capital_deployed,
       SUM(COALESCE(ra.profit_per_ac_day, 0) * mr.num_assigned) AS daily_profit
FROM my_routes mr
JOIN route_aircraft ra
     ON ra.origin_id = mr.origin_id
    AND ra.dest_id = mr.dest_id
    AND ra.aircraft_id = mr.aircraft_id
    AND ra.is_valid = 1
JOIN aircraft ac ON mr.aircraft_id = ac.id
JOIN airports ho ON mr.origin_id = ho.id
GROUP BY ho.id, ho.iata
"""


def _hub_roi_summary() -> dict:
    """Per-hub capital, daily profit, payback — from my_routes × route_aircraft."""
    try:
        conn = get_db()
        try:
            raw = fetch_all(conn, _HUB_ROI_SQL)
        finally:
            conn.close()
    except FileNotFoundError:
        return {
            "hub_roi_rows": [],
            "hub_roi_totals": {
                "capital": 0.0,
                "daily": 0.0,
                "routes": 0,
                "aircraft_deployed": 0,
                "payback_days": None,
            },
        }

    rows: list[dict] = []
    for r in raw:
        routes = int(r["routes"] or 0)
        deployed = int(r["aircraft_deployed"] or 0)
        cap = float(r["capital_deployed"] or 0)
        daily = float(r["daily_profit"] or 0)
        avg_pa = daily / deployed if deployed else 0.0
        payback = cap / daily if daily > 1e-9 else None
        rows.append(
            {
                "hub": r["hub"],
                "routes": routes,
                "aircraft_deployed": deployed,
                "capital_deployed": cap,
                "daily_profit": daily,
                "avg_profit_per_ac": avg_pa,
                "payback_days": payback,
                "is_worst": False,
            }
        )

    if rows:
        min_avg = min(x["avg_profit_per_ac"] for x in rows)
        for x in rows:
            x["is_worst"] = abs(x["avg_profit_per_ac"] - min_avg) < 1e-9
        rows.sort(key=lambda x: x["avg_profit_per_ac"])

    totals = {
        "capital": sum(x["capital_deployed"] for x in rows),
        "daily": sum(x["daily_profit"] for x in rows),
        "routes": sum(x["routes"] for x in rows),
        "aircraft_deployed": sum(x["aircraft_deployed"] for x in rows),
    }
    totals["payback_days"] = (
        totals["capital"] / totals["daily"] if totals["daily"] > 1e-9 else None
    )

    return {"hub_roi_rows": rows, "hub_roi_totals": totals}


@router.get("/hub-roi", response_class=HTMLResponse)
def page_hub_roi(request: Request):
    ctx = base_context(request)
    ctx.update(_hub_roi_summary())
    return templates.TemplateResponse(request, "hub_roi.html", ctx)


@router.get("/scenarios", response_class=HTMLResponse)
def page_scenarios(request: Request):
    ctx = base_context(request)
    ctx.update({"hubs": _hub_iatas_from_my_routes()})
    try:
        conn = get_db()
        try:
            cfg = load_extract_config(conn)
            if cfg:
                df, dc = float(cfg.fuel_price), float(cfg.co2_price)
            else:
                row = fetch_one(
                    conn,
                    "SELECT fuel_price, co2_price FROM route_aircraft WHERE fuel_price IS NOT NULL LIMIT 1",
                )
                if row and row.get("fuel_price") is not None:
                    df = float(row["fuel_price"])
                    dc = float(row["co2_price"] or UserConfig().co2_price)
                else:
                    df, dc = UserConfig().fuel_price, UserConfig().co2_price
        finally:
            conn.close()
    except FileNotFoundError:
        df, dc = UserConfig().fuel_price, UserConfig().co2_price
    ctx["default_fuel"] = df
    ctx["default_co2"] = dc
    ctx.update(_saved_filters_bar_context("scenarios"))
    return templates.TemplateResponse(request, "scenarios.html", ctx)


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


@router.get("/settings", response_class=HTMLResponse)
def page_settings(request: Request):
    ctx = base_context(request)
    ctx["landing_paths"] = sorted(ALLOWED_LANDING_PATHS)
    ctx["app_version"] = _package_version()
    return templates.TemplateResponse(request, "settings.html", ctx)
