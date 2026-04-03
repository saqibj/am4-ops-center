#!/usr/bin/env python3
"""
AM4 RouteMine — bulk route extraction CLI.

Usage:
    python main.py extract --hubs KHI,DXB --mode easy --ci 200
    python main.py extract --refresh-hubs --hubs KHI,DXB
    python main.py export --format csv --output ./exports/
    python main.py query --hub KHI --aircraft b738 --top 20
    python main.py dashboard --db am4_data.db --port 8000
    python main.py fleet import --file fleet.csv
    python main.py fleet import --replace --file fleet.csv
    python main.py routes import --file my_routes.csv
    python main.py recommend --hub KHI --budget 500000000
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from config import GameMode, UserConfig
from database.schema import get_connection


def _config_from_extract_args(args: argparse.Namespace) -> UserConfig:
    cfg = UserConfig(
        game_mode=GameMode.EASY if args.mode == "easy" else GameMode.REALISM,
        cost_index=int(args.ci),
        reputation=float(args.reputation),
        max_workers=int(args.workers),
    )
    if args.all_hubs:
        cfg.hubs = []
    elif args.hubs:
        cfg.hubs = [x.strip() for x in args.hubs.split(",") if x.strip()]
    if args.aircraft:
        cfg.aircraft_filter = [x.strip() for x in args.aircraft.split(",") if x.strip()]
    return cfg


def cmd_extract(args: argparse.Namespace) -> None:
    from am4.utils.db import init

    init()
    cfg = _config_from_extract_args(args)

    if args.refresh_hubs:
        if args.all_hubs:
            print("Error: --refresh-hubs cannot be used with --all-hubs", file=sys.stderr)
            sys.exit(2)
        if not args.hubs or not str(args.hubs).strip():
            print("Error: --refresh-hubs requires --hubs IATA1,IATA2", file=sys.stderr)
            sys.exit(2)
        from extractors.routes import refresh_hubs

        hub_list = [x.strip() for x in args.hubs.split(",") if x.strip()]
        refresh_hubs(args.db, cfg, hub_list)
        print(f"Refreshed routes for {len(hub_list)} hub(s).")
        return

    if not args.all_hubs and not args.hubs:
        print("Error: specify --hubs IATA1,IATA2 or --all-hubs", file=sys.stderr)
        sys.exit(2)
    from extractors.routes import run_bulk_extraction

    run_bulk_extraction(args.db, cfg)


def cmd_export(args: argparse.Namespace) -> None:
    if args.format == "csv":
        from exporters.csv_export import export_csv

        export_csv(args.db, args.output)
        print(f"CSV export written to {args.output}")
    else:
        from exporters.excel_export import export_excel

        export_excel(args.db, args.output)
        print(f"Excel export written to {args.output}")


def cmd_query(args: argparse.Namespace) -> None:
    sort_map = {
        "profit": "ra.profit_per_ac_day",
        "contribution": "ra.contribution",
        "income": "ra.income_per_ac_day",
    }
    sort_col = sort_map[args.sort]
    conn = get_connection(args.db)
    sql = f"""
    SELECT a_orig.iata AS hub, a_dest.iata AS destination, ac.shortname AS aircraft, ac.type AS ac_type,
           ra.profit_per_trip, ra.trips_per_day, ra.profit_per_ac_day, ra.contribution,
           ra.income_per_ac_day, ra.flight_time_hrs, ra.distance_km, ra.needs_stopover, ra.stopover_iata
    FROM route_aircraft ra
    JOIN airports a_orig ON ra.origin_id = a_orig.id
    JOIN airports a_dest ON ra.dest_id = a_dest.id
    JOIN aircraft ac ON ra.aircraft_id = ac.id
    WHERE ra.is_valid = 1 AND UPPER(a_orig.iata) = UPPER(?)
    """
    params: list = [args.hub.strip()]
    if args.aircraft:
        sql += " AND LOWER(ac.shortname) = LOWER(?)"
        params.append(args.aircraft.strip())
    if args.type:
        sql += " AND UPPER(ac.type) = UPPER(?)"
        params.append(args.type.strip())
    sql += f" ORDER BY {sort_col} DESC LIMIT ?"
    params.append(int(args.top))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        print("No rows.")
        return
    cols = rows[0].keys()
    header = "\t".join(cols)
    print(header)
    for r in rows:
        print("\t".join(str(r[c]) for c in cols))


def cmd_dashboard(args: argparse.Namespace) -> None:
    import uvicorn

    os.environ["AM4_ROUTEMINE_DB"] = str(Path(args.db).resolve())
    uvicorn.run(
        "dashboard.server:app",
        host=args.host,
        port=int(args.port),
        reload=True,
    )


def _add_db(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", type=str, default="am4_data.db", help="SQLite database path")


def cmd_fleet(args: argparse.Namespace) -> None:
    from commands.airline import fleet_export, fleet_import, fleet_list

    if args.fleet_cmd == "import":
        mode = "replace" if getattr(args, "replace", False) else "merge"
        fleet_import(args.db, args.file, mode=mode)
    elif args.fleet_cmd == "export":
        fleet_export(args.db, args.output)
    else:
        fleet_list(args.db)


def cmd_routes(args: argparse.Namespace) -> None:
    from commands.airline import routes_export, routes_import

    if args.routes_cmd == "import":
        mode = "replace" if getattr(args, "replace", False) else "merge"
        routes_import(args.db, args.file, mode=mode)
    else:
        routes_export(args.db, args.output)


def cmd_recommend(args: argparse.Namespace) -> None:
    from commands.airline import recommend

    recommend(args.db, args.hub, args.budget, args.top)


def main() -> None:
    parser = argparse.ArgumentParser(description="AM4 RouteMine — bulk route data extractor")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser(
        "extract",
        help="Run extraction: full rebuild by default, or hub-only refresh with --refresh-hubs",
    )
    ex.add_argument("--hubs", type=str, help="Comma-separated IATA codes (e.g. KHI,DXB)")
    ex.add_argument("--all-hubs", action="store_true", help="Use every airport as a hub (full rebuild only)")
    ex.add_argument(
        "--refresh-hubs",
        action="store_true",
        help="Recompute routes only for --hubs (no full master replace; requires --hubs, not --all-hubs)",
    )
    ex.add_argument("--mode", choices=["easy", "realism"], default="easy")
    ex.add_argument("--ci", type=int, default=200, help="Cost index hint (stored from am4 result; am4 optimizes CI)")
    ex.add_argument("--reputation", type=float, default=87.0)
    ex.add_argument("--aircraft", type=str, help="Limit to aircraft shortnames, e.g. b738,a388")
    ex.add_argument("--db", type=str, default="am4_data.db")
    ex.add_argument("--workers", type=int, default=4)
    ex.set_defaults(func=cmd_extract)

    exp = sub.add_parser("export", help="Export DB to CSV or Excel")
    exp.add_argument("--format", choices=["csv", "excel"], default="csv")
    exp.add_argument("--output", type=str, default="./exports/")
    exp.add_argument("--db", type=str, default="am4_data.db")
    exp.set_defaults(func=cmd_export)

    q = sub.add_parser("query", help="Query extracted SQLite data")
    q.add_argument("--hub", type=str, required=True)
    q.add_argument("--aircraft", type=str)
    q.add_argument("--type", choices=["pax", "cargo", "vip"])
    q.add_argument("--top", type=int, default=20)
    q.add_argument("--sort", choices=["profit", "contribution", "income"], default="profit")
    q.add_argument("--db", type=str, default="am4_data.db")
    q.set_defaults(func=cmd_query)

    dash = sub.add_parser("dashboard", help="Launch web dashboard")
    dash.add_argument("--db", type=str, default="am4_data.db")
    dash.add_argument("--port", type=int, default=8000)
    dash.add_argument("--host", type=str, default="0.0.0.0")
    dash.set_defaults(func=cmd_dashboard)

    fleet_p = sub.add_parser("fleet", help="My airline fleet table (my_fleet) CSV")
    fleet_sp = fleet_p.add_subparsers(dest="fleet_cmd", required=True)
    f_imp = fleet_sp.add_parser(
        "import",
        help="Import fleet.csv: shortname,count,notes (default: merge quantities on duplicate)",
    )
    _add_db(f_imp)
    f_imp.add_argument("--file", type=str, required=True)
    f_imp_mx = f_imp.add_mutually_exclusive_group()
    f_imp_mx.add_argument(
        "--merge",
        action="store_true",
        help="On duplicate shortname, add to stored quantity (default)",
    )
    f_imp_mx.add_argument(
        "--replace",
        action="store_true",
        help="On duplicate shortname, set quantity from CSV (overwrite)",
    )
    f_exp = fleet_sp.add_parser("export", help="Export my_fleet to CSV")
    _add_db(f_exp)
    f_exp.add_argument("--output", type=str, required=True)
    f_lst = fleet_sp.add_parser("list", help="Print my_fleet (TSV)")
    _add_db(f_lst)
    fleet_p.set_defaults(func=cmd_fleet)

    routes_p = sub.add_parser("routes", help="My airline routes table (my_routes) CSV")
    routes_sp = routes_p.add_subparsers(dest="routes_cmd", required=True)
    r_imp = routes_sp.add_parser(
        "import",
        help="Import my_routes.csv: hub,destination,aircraft,num_assigned,notes (default: merge on duplicate)",
    )
    _add_db(r_imp)
    r_imp.add_argument("--file", type=str, required=True)
    r_imp_mx = r_imp.add_mutually_exclusive_group()
    r_imp_mx.add_argument(
        "--merge",
        action="store_true",
        help="On duplicate key, add num_assigned to stored value (default)",
    )
    r_imp_mx.add_argument(
        "--replace",
        action="store_true",
        help="On duplicate key, set num_assigned from CSV (overwrite)",
    )
    r_exp = routes_sp.add_parser("export", help="Export my_routes to CSV")
    _add_db(r_exp)
    r_exp.add_argument("--output", type=str, required=True)
    routes_p.set_defaults(func=cmd_routes)

    rec = sub.add_parser(
        "recommend",
        help="Recommend aircraft at a hub within budget (from extracted routes)",
    )
    _add_db(rec)
    rec.add_argument("--hub", type=str, required=True, help="Origin hub IATA")
    rec.add_argument("--budget", type=int, required=True, help="Max aircraft cost ($)")
    rec.add_argument("--top", type=int, default=25, help="Max rows to print")
    rec.set_defaults(func=cmd_recommend)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
