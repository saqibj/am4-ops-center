"""Bulk route extraction using am4 RoutesSearch."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from config import GameMode, UserConfig
from database.schema import clear_route_tables, create_schema, get_connection, replace_master_tables
from extractors.aircraft import extract_all_aircraft
from extractors.airports import extract_all_airports

if TYPE_CHECKING:
    from am4.utils.game import User as Am4User


def build_am4_user(cfg: UserConfig) -> "Am4User":
    """Map RouteMine config to am4 User (CI is optimized inside am4; not set on User)."""
    from am4.utils.game import User
    from am4.utils.route import AircraftRoute

    realism = cfg.game_mode == GameMode.REALISM
    user = User.Default(realism=realism)
    user.game_mode = User.GameMode.REALISM if realism else User.GameMode.EASY
    user.fuel_price = int(cfg.fuel_price)
    user.co2_price = int(cfg.co2_price)
    user.fuel_training = int(cfg.fuel_training)
    user.co2_training = int(cfg.co2_training)
    user.repair_training = int(cfg.repair_training)
    user.accumulated_count = int(cfg.total_planes_owned)
    load = AircraftRoute.estimate_load(cfg.reputation)
    user.load = load
    user.cargo_load = load
    return user


def _aircraft_route_options(cfg: UserConfig) -> Any:
    from am4.utils.route import AircraftRoute

    opts = AircraftRoute.Options(
        sort_by=AircraftRoute.Options.SortBy.PER_AC_PER_DAY,
        tpd_mode=AircraftRoute.Options.TPDMode.AUTO,
    )
    if cfg.max_flight_time_hours >= 0:
        opts.max_flight_time = float(cfg.max_flight_time_hours)
    return opts


def _ticket_values(acr: Any) -> tuple[float | None, float | None, float | None]:
    t = acr.ticket
    if hasattr(t, "y"):
        return float(t.y), float(t.j), float(t.f)
    return float(t.l), float(t.h), None


def _config_algorithm_name(cfg: Any) -> str | None:
    alg = getattr(cfg, "algorithm", None)
    if alg is None:
        return None
    return getattr(alg, "name", str(alg))


def extract_routes_for_hub(
    hub_iata: str,
    aircraft_rows: list[dict],
    cfg: UserConfig,
    user: Any,
    options: Any,
    game_mode_label: str,
) -> tuple[list[dict], list[dict]]:
    """Return (route_aircraft rows as dicts, route_demands rows as dicts)."""
    from am4.utils.aircraft import Aircraft
    from am4.utils.airport import Airport
    from am4.utils.route import RoutesSearch

    route_rows: list[dict] = []
    demand_rows: list[dict] = []
    try:
        hub_res = Airport.search(hub_iata.strip())
        hub = hub_res.ap
    except Exception:
        return route_rows, demand_rows

    if not hub.valid:
        return route_rows, demand_rows

    want_stop = cfg.include_stopovers
    min_profit = cfg.min_profit_per_day
    filters = {s.strip().lower() for s in cfg.aircraft_filter if s.strip()}

    for row in aircraft_rows:
        sn = row.get("shortname") or ""
        if filters and sn.lower() not in filters:
            continue
        try:
            ac = Aircraft.search(sn).ac
        except Exception:
            continue
        if not ac.valid:
            continue
        if int(ac.rwy) > int(hub.rwy):
            continue

        try:
            search = RoutesSearch(ap0=[hub], ac=ac, options=options, user=user)
            destinations = search.get()
        except Exception:
            continue

        for dest in destinations:
            acr = dest.ac_route
            if not acr.valid:
                continue
            if not want_stop and acr.needs_stopover:
                continue

            tpd = int(acr.trips_per_day_per_ac)
            profit_day = float(acr.profit) * tpd
            if profit_day < min_profit:
                continue

            pd = acr.route.pax_demand
            demand_rows.append(
                {
                    "origin_id": hub.id,
                    "dest_id": dest.airport.id,
                    "distance_km": float(acr.route.direct_distance),
                    "demand_y": int(pd.y),
                    "demand_j": int(pd.j),
                    "demand_f": int(pd.f),
                }
            )

            cfg_obj = acr.config
            if ac.type.name == "CARGO":
                config_y = int(cfg_obj.l)
                config_j = int(cfg_obj.h)
                config_f = None
            else:
                config_y = int(cfg_obj.y)
                config_j = int(cfg_obj.j)
                config_f = int(cfg_obj.f)

            ty, tj, tf = _ticket_values(acr)
            stop_iata = None
            total_dist = float(acr.route.direct_distance)
            if acr.needs_stopover and acr.stopover.exists:
                stop_iata = acr.stopover.airport.iata
                total_dist = float(acr.stopover.full_distance)

            route_rows.append(
                {
                    "origin_id": hub.id,
                    "dest_id": dest.airport.id,
                    "aircraft_id": ac.id,
                    "distance_km": float(acr.route.direct_distance),
                    "config_y": config_y,
                    "config_j": config_j,
                    "config_f": config_f,
                    "config_algorithm": _config_algorithm_name(cfg_obj),
                    "ticket_y": ty,
                    "ticket_j": tj,
                    "ticket_f": tf,
                    "income": float(acr.income),
                    "fuel_cost": float(acr.fuel),
                    "co2_cost": float(acr.co2),
                    "repair_cost": float(acr.repair_cost),
                    "acheck_cost": float(acr.acheck_cost),
                    "profit_per_trip": float(acr.profit),
                    "flight_time_hrs": float(acr.flight_time),
                    "trips_per_day": tpd,
                    "num_aircraft": int(acr.num_ac),
                    "profit_per_ac_day": profit_day,
                    "income_per_ac_day": float(acr.income) * tpd,
                    "contribution": float(acr.contribution),
                    "needs_stopover": 1 if acr.needs_stopover else 0,
                    "stopover_iata": stop_iata,
                    "total_distance": total_dist,
                    "ci": int(acr.ci),
                    "warnings": json.dumps([w.to_str() for w in acr.warnings]),
                    "is_valid": 1 if acr.valid else 0,
                    "game_mode": game_mode_label,
                }
            )

    return route_rows, demand_rows


ROUTE_INSERT_SQL = """
INSERT INTO route_aircraft (
    origin_id, dest_id, aircraft_id, distance_km,
    config_y, config_j, config_f, config_algorithm,
    ticket_y, ticket_j, ticket_f,
    income, fuel_cost, co2_cost, repair_cost, acheck_cost, profit_per_trip,
    flight_time_hrs, trips_per_day, num_aircraft,
    profit_per_ac_day, income_per_ac_day,
    contribution,
    needs_stopover, stopover_iata, total_distance,
    ci, warnings, is_valid, game_mode
) VALUES (
    :origin_id, :dest_id, :aircraft_id, :distance_km,
    :config_y, :config_j, :config_f, :config_algorithm,
    :ticket_y, :ticket_j, :ticket_f,
    :income, :fuel_cost, :co2_cost, :repair_cost, :acheck_cost, :profit_per_trip,
    :flight_time_hrs, :trips_per_day, :num_aircraft,
    :profit_per_ac_day, :income_per_ac_day,
    :contribution,
    :needs_stopover, :stopover_iata, :total_distance,
    :ci, :warnings, :is_valid, :game_mode
)
"""

DEMAND_UPSERT_SQL = """
INSERT OR REPLACE INTO route_demands (
    origin_id, dest_id, distance_km, demand_y, demand_j, demand_f
) VALUES (?, ?, ?, ?, ?, ?)
"""


def _insert_batches(
    conn: sqlite3.Connection,
    route_rows: list[dict],
    demand_pairs: dict[tuple[int, int], tuple],
    batch_size: int = 1000,
) -> None:
    cur = conn.cursor()
    for i in range(0, len(route_rows), batch_size):
        chunk = route_rows[i : i + batch_size]
        cur.executemany(ROUTE_INSERT_SQL, chunk)
    for key, tup in demand_pairs.items():
        cur.execute(DEMAND_UPSERT_SQL, tup)
    conn.commit()


def run_bulk_extraction(db_path: str, cfg: UserConfig) -> None:
    """Orchestrate aircraft, airports, and hub×aircraft route extraction."""
    from tqdm import tqdm

    conn = get_connection(db_path)
    create_schema(conn)
    clear_route_tables(conn)
    replace_master_tables(conn)

    print("[1/3] Extracting aircraft…")
    aircraft_rows = extract_all_aircraft(conn)
    print(f"    → {len(aircraft_rows)} aircraft")

    print("[2/3] Extracting airports…")
    airport_rows = extract_all_airports(conn, cfg)
    print(f"    → {len(airport_rows)} airports")

    if cfg.hubs:
        hubs = [h.strip().upper() for h in cfg.hubs if h.strip()]
    else:
        hubs = [a["iata"] for a in airport_rows if a.get("iata")]

    if cfg.hub_filter:
        allow = {h.strip().upper() for h in cfg.hub_filter if h.strip()}
        hubs = [h for h in hubs if h in allow]

    user = build_am4_user(cfg)
    options = _aircraft_route_options(cfg)
    game_mode_label = cfg.game_mode.value

    print(f"[3/3] Computing routes for {len(hubs)} hubs × {len(aircraft_rows)} aircraft (workers={cfg.max_workers})…")

    all_routes: list[dict] = []
    demand_map: dict[tuple[int, int], tuple] = {}

    def merge_demands(demands: list[dict]) -> None:
        for d in demands:
            key = (int(d["origin_id"]), int(d["dest_id"]))
            if key not in demand_map:
                demand_map[key] = (
                    key[0],
                    key[1],
                    float(d["distance_km"]),
                    int(d["demand_y"]),
                    int(d["demand_j"]),
                    int(d["demand_f"]),
                )

    workers = max(1, int(cfg.max_workers))

    if workers == 1:
        for hub in tqdm(hubs):
            rr, dd = extract_routes_for_hub(hub, aircraft_rows, cfg, user, options, game_mode_label)
            all_routes.extend(rr)
            merge_demands(dd)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(
                    extract_routes_for_hub,
                    hub,
                    aircraft_rows,
                    cfg,
                    user,
                    options,
                    game_mode_label,
                ): hub
                for hub in hubs
            }
            for fut in tqdm(as_completed(futs), total=len(futs), desc="Hubs"):
                rr, dd = fut.result()
                all_routes.extend(rr)
                merge_demands(dd)

    _insert_batches(conn, all_routes, demand_map)
    print(f"    → {len(all_routes)} route rows, {len(demand_map)} origin–destination demand rows")
    conn.close()
