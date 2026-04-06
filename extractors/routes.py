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
ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
    distance_km = excluded.distance_km,
    config_y = excluded.config_y,
    config_j = excluded.config_j,
    config_f = excluded.config_f,
    config_algorithm = excluded.config_algorithm,
    ticket_y = excluded.ticket_y,
    ticket_j = excluded.ticket_j,
    ticket_f = excluded.ticket_f,
    income = excluded.income,
    fuel_cost = excluded.fuel_cost,
    co2_cost = excluded.co2_cost,
    repair_cost = excluded.repair_cost,
    acheck_cost = excluded.acheck_cost,
    profit_per_trip = excluded.profit_per_trip,
    flight_time_hrs = excluded.flight_time_hrs,
    trips_per_day = excluded.trips_per_day,
    num_aircraft = excluded.num_aircraft,
    profit_per_ac_day = excluded.profit_per_ac_day,
    income_per_ac_day = excluded.income_per_ac_day,
    contribution = excluded.contribution,
    needs_stopover = excluded.needs_stopover,
    stopover_iata = excluded.stopover_iata,
    total_distance = excluded.total_distance,
    ci = excluded.ci,
    warnings = excluded.warnings,
    is_valid = excluded.is_valid,
    game_mode = excluded.game_mode,
    extracted_at = CURRENT_TIMESTAMP
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


def _aircraft_rows_from_db(conn: sqlite3.Connection) -> list[dict]:
    """Same shape as extract_all_aircraft() output for extract_routes_for_hub."""
    rows = conn.execute(
        """
        SELECT id, shortname, name, type
        FROM aircraft
        ORDER BY shortname COLLATE NOCASE
        """
    ).fetchall()
    return [
        {"id": int(r["id"]), "shortname": r["shortname"], "name": r["name"], "type": r["type"]}
        for r in rows
    ]


def upsert_airport_from_am4(
    conn: sqlite3.Connection, cfg: UserConfig, hub_iata: str
) -> tuple[int | None, str | None]:
    """Return (airport_id, None) or (None, error_message). Persists airport if missing locally."""
    from am4.utils.airport import Airport

    iata_key = hub_iata.strip().upper()
    row = conn.execute(
        """
        SELECT id FROM airports
        WHERE iata IS NOT NULL AND UPPER(TRIM(iata)) = ? LIMIT 1
        """,
        (iata_key,),
    ).fetchone()
    if row:
        return int(row[0]), None
    try:
        hub_res = Airport.search(hub_iata.strip())
        ap = hub_res.ap
    except Exception as exc:
        return None, f"Airport lookup failed: {exc}"
    if not ap.valid:
        return None, "Airport is not valid in AM4"
    if int(ap.rwy) < int(cfg.min_runway):
        return None, f"Runway {ap.rwy} below min_runway ({cfg.min_runway})"
    conn.execute(
        """
        INSERT OR REPLACE INTO airports (
            id, iata, icao, name, fullname, country, continent, lat, lng, rwy, rwy_codes,
            market, hub_cost
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ap.id,
            ap.iata,
            ap.icao,
            ap.name,
            ap.fullname,
            ap.country,
            ap.continent,
            float(ap.lat),
            float(ap.lng),
            int(ap.rwy),
            ap.rwy_codes,
            int(ap.market),
            int(ap.hub_cost),
        ),
    )
    conn.commit()
    return int(ap.id), None


def _my_hubs_mark_running(conn: sqlite3.Connection, airport_id: int) -> None:
    cur = conn.execute(
        """
        UPDATE my_hubs
        SET last_extract_status = 'running', last_extract_error = NULL, updated_at = datetime('now')
        WHERE airport_id = ?
        """,
        (airport_id,),
    )
    if cur.rowcount:
        conn.commit()


def _my_hubs_mark_ok(conn: sqlite3.Connection, airport_id: int) -> None:
    cur = conn.execute(
        """
        UPDATE my_hubs
        SET last_extract_status = 'ok', last_extract_error = NULL,
            last_extracted_at = datetime('now'), updated_at = datetime('now')
        WHERE airport_id = ?
        """,
        (airport_id,),
    )
    if cur.rowcount:
        conn.commit()


def _my_hubs_mark_error(conn: sqlite3.Connection, airport_id: int | None, hub_iata: str, msg: str) -> None:
    if airport_id is not None:
        cur = conn.execute(
            """
            UPDATE my_hubs
            SET last_extract_status = 'error', last_extract_error = ?, updated_at = datetime('now')
            WHERE airport_id = ?
            """,
            (msg, airport_id),
        )
        if cur.rowcount:
            conn.commit()
            return
    cur2 = conn.execute(
        """
        UPDATE my_hubs
        SET last_extract_status = 'error', last_extract_error = ?, updated_at = datetime('now')
        WHERE airport_id IN (
            SELECT id FROM airports
            WHERE iata IS NOT NULL AND UPPER(TRIM(iata)) = UPPER(TRIM(?))
        )
        """,
        (msg, hub_iata.strip()),
    )
    if cur2.rowcount:
        conn.commit()


def _delete_routes_for_origin(conn: sqlite3.Connection, origin_id: int) -> None:
    conn.execute("DELETE FROM route_aircraft WHERE origin_id = ?", (origin_id,))
    conn.execute("DELETE FROM route_demands WHERE origin_id = ?", (origin_id,))
    conn.commit()


def _demands_to_map(demand_rows: list[dict]) -> dict[tuple[int, int], tuple]:
    demand_map: dict[tuple[int, int], tuple] = {}
    for d in demand_rows:
        key = (int(d["origin_id"]), int(d["dest_id"]))
        demand_map[key] = (
            key[0],
            key[1],
            float(d["distance_km"]),
            int(d["demand_y"]),
            int(d["demand_j"]),
            int(d["demand_f"]),
        )
    return demand_map


def refresh_single_hub_conn(conn: sqlite3.Connection, cfg: UserConfig, hub_iata: str) -> None:
    """
    Recompute route_aircraft and route_demands for one origin hub only.
    Does not clear other hubs or replace aircraft/airports master tables.
    """
    raw_iata = hub_iata.strip()
    n_ac = int(conn.execute("SELECT COUNT(*) AS c FROM aircraft").fetchone()["c"])
    if n_ac == 0:
        raise RuntimeError(
            "No aircraft master data in the database. Run a full extract once, e.g. "
            "python main.py extract --all-hubs"
        )

    ap_id, err = upsert_airport_from_am4(conn, cfg, raw_iata)
    if err is not None or ap_id is None:
        _my_hubs_mark_error(conn, ap_id, raw_iata, err or "Unknown airport")
        raise ValueError(err or "Unknown airport")

    _my_hubs_mark_running(conn, ap_id)

    try:
        _delete_routes_for_origin(conn, ap_id)
        aircraft_rows = _aircraft_rows_from_db(conn)
        user = build_am4_user(cfg)
        options = _aircraft_route_options(cfg)
        game_mode_label = cfg.game_mode.value
        row = conn.execute("SELECT iata FROM airports WHERE id = ?", (ap_id,)).fetchone()
        iata_for_extract = (row["iata"] or raw_iata).strip() if row else raw_iata
        rr, dd = extract_routes_for_hub(
            iata_for_extract, aircraft_rows, cfg, user, options, game_mode_label
        )
        _insert_batches(conn, rr, _demands_to_map(dd))
        _my_hubs_mark_ok(conn, ap_id)
    except Exception as exc:
        err_txt = str(exc)[:1024] if str(exc) else type(exc).__name__
        _my_hubs_mark_error(conn, ap_id, raw_iata, err_txt)
        raise


def refresh_single_hub(db_path: str, cfg: UserConfig, hub_iata: str) -> None:
    """Open DB, ensure schema, refresh one hub, close."""
    conn = get_connection(db_path)
    try:
        create_schema(conn)
        refresh_single_hub_conn(conn, cfg, hub_iata)
    finally:
        conn.close()


def refresh_hubs(db_path: str, cfg: UserConfig, hub_iatas: list[str]) -> None:
    """Refresh each hub in sequence; other origins are left unchanged."""
    conn = get_connection(db_path)
    try:
        create_schema(conn)
        for h in hub_iatas:
            s = (h or "").strip()
            if not s:
                continue
            refresh_single_hub_conn(conn, cfg, s)
    finally:
        conn.close()


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
