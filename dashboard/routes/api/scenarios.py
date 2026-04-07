"""Fuel & CO2 price what-if vs extraction baselines stored on ``route_aircraft``."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from config import UserConfig
from dashboard.db import fetch_all, fetch_one, get_db
from dashboard.server import templates
from database.schema import load_extract_config

router = APIRouter()


def _fallback_baseline_prices(conn) -> tuple[float, float]:
    cfg = load_extract_config(conn)
    if cfg:
        return float(cfg.fuel_price), float(cfg.co2_price)
    row = fetch_one(
        conn,
        "SELECT fuel_price, co2_price FROM route_aircraft WHERE fuel_price IS NOT NULL LIMIT 1",
    )
    if row and row.get("fuel_price") is not None:
        fp = float(row["fuel_price"])
        cp = float(row["co2_price"]) if row.get("co2_price") is not None else UserConfig().co2_price
        return fp, cp
    return UserConfig().fuel_price, UserConfig().co2_price


def _fetch_scenario_rows(conn, scope: str, hub: str) -> list[dict]:
    hub = (hub or "").strip()
    hub_sql = ""
    params: list = []
    if hub:
        hub_sql = " AND UPPER(TRIM(ho.iata)) = UPPER(TRIM(?))"
        params.append(hub)

    if scope == "all":
        sql = f"""
        SELECT ra.profit_per_trip, ra.trips_per_day, ra.fuel_cost, ra.co2_cost,
               ra.fuel_price, ra.co2_price, ra.profit_per_ac_day,
               1 AS num_assigned,
               ho.iata AS hub, hd.iata AS dest, ac.shortname AS ac
        FROM route_aircraft ra
        JOIN airports ho ON ra.origin_id = ho.id
        JOIN airports hd ON ra.dest_id = hd.id
        JOIN aircraft ac ON ra.aircraft_id = ac.id
        WHERE ra.is_valid = 1
        {hub_sql}
        """
        return fetch_all(conn, sql, params)

    sql = f"""
    SELECT ra.profit_per_trip, ra.trips_per_day, ra.fuel_cost, ra.co2_cost,
           ra.fuel_price, ra.co2_price, ra.profit_per_ac_day,
           mr.num_assigned,
           ho.iata AS hub, hd.iata AS dest, ac.shortname AS ac
    FROM my_routes mr
    JOIN route_aircraft ra
         ON ra.origin_id = mr.origin_id
        AND ra.dest_id = mr.dest_id
        AND ra.aircraft_id = mr.aircraft_id
        AND ra.is_valid = 1
    JOIN airports ho ON mr.origin_id = ho.id
    JOIN airports hd ON mr.dest_id = hd.id
    JOIN aircraft ac ON ra.aircraft_id = ac.id
    WHERE 1 = 1
    {hub_sql}
    """
    return fetch_all(conn, sql, params)


def _scenario_profit_per_ac_day(
    row: dict,
    scenario_fuel: float,
    scenario_co2: float,
    fb: float,
    cb: float,
) -> float:
    fp0 = float(row["fuel_price"] if row["fuel_price"] is not None else fb)
    cp0 = float(row["co2_price"] if row["co2_price"] is not None else cb)
    if fp0 <= 1e-12:
        fp0 = max(float(UserConfig().fuel_price), 1e-9)
    if cp0 <= 1e-12:
        cp0 = max(float(UserConfig().co2_price), 1e-9)
    fuel_c = float(row["fuel_cost"] or 0)
    co2_c = float(row["co2_cost"] or 0)
    p_trip = float(row["profit_per_trip"] or 0)
    tpd = int(row["trips_per_day"] or 0)
    burn = fuel_c / fp0
    quota = co2_c / cp0
    new_fuel = burn * scenario_fuel
    new_co2 = quota * scenario_co2
    new_pt = p_trip + (fuel_c - new_fuel) + (co2_c - new_co2)
    return new_pt * tpd


@router.get("/scenarios", response_class=HTMLResponse)
def api_scenarios(
    request: Request,
    fuel_price: float = Query(700.0, ge=0.0, le=10_000.0),
    co2_price: float = Query(120.0, ge=0.0, le=2000.0),
    scope: str = Query("my_routes"),
    hub: str = Query(""),
):
    scope_norm = "all" if scope.strip().lower() == "all" else "my_routes"
    try:
        conn = get_db()
    except FileNotFoundError:
        return HTMLResponse(
            "<p class='text-amber-400'>Database not found. Configure AM4_ROUTEMINE_DB or run an extract.</p>"
        )

    try:
        fb, cb = _fallback_baseline_prices(conn)
        rows = _fetch_scenario_rows(conn, scope_norm, hub)
    finally:
        conn.close()

    baseline_daily_total = 0.0
    scenario_daily_total = 0.0
    enriched: list[dict] = []

    for r in rows:
        mult = max(1, int(r.get("num_assigned") or 1))
        b_ac = float(r["profit_per_ac_day"] or 0)
        s_ac = _scenario_profit_per_ac_day(r, fuel_price, co2_price, fb, cb)
        bday = b_ac * mult
        sday = s_ac * mult
        baseline_daily_total += bday
        scenario_daily_total += sday
        enriched.append(
            {
                **r,
                "baseline_daily": bday,
                "scenario_daily": sday,
                "delta_daily": sday - bday,
                "scenario_per_ac_day": s_ac,
            }
        )

    flip_neg_to_pos = sum(
        1
        for e in enriched
        if float(e["profit_per_ac_day"] or 0) <= 0 and e["scenario_per_ac_day"] > 0
    )
    flip_pos_to_neg = sum(
        1
        for e in enriched
        if float(e["profit_per_ac_day"] or 0) > 0 and e["scenario_per_ac_day"] <= 0
    )

    enriched.sort(key=lambda x: x["delta_daily"])
    worst10 = enriched[:10]
    best10 = sorted(enriched, key=lambda x: x["delta_daily"], reverse=True)[:10]

    delta_total = scenario_daily_total - baseline_daily_total
    pct_change = (
        (delta_total / baseline_daily_total * 100.0) if abs(baseline_daily_total) > 1e-9 else None
    )

    return templates.TemplateResponse(
        request,
        "partials/scenarios_results.html",
        {
            "rows": enriched,
            "extraction_baseline_prices": (fb, cb),
            "scenario_prices": (fuel_price, co2_price),
            "baseline_daily_total": baseline_daily_total,
            "scenario_daily_total": scenario_daily_total,
            "delta_total": delta_total,
            "pct_change": pct_change,
            "flip_neg_to_pos": flip_neg_to_pos,
            "flip_pos_to_neg": flip_pos_to_neg,
            "worst10": worst10,
            "best10": best10,
            "scope": scope_norm,
            "n_rows": len(enriched),
        },
    )
