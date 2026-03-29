#!/usr/bin/env python3
"""
AM4 RouteMine — bulk route extraction CLI.

Usage:
    python main.py extract --hubs KHI,DXB --mode easy --ci 200
    python main.py extract --all-hubs --mode easy
    python main.py export --format csv --output ./exports/
    python main.py query --hub KHI --aircraft b738 --top 20
    python main.py dashboard --db am4_data.db --port 8501
"""

from __future__ import annotations

import argparse
import os
import subprocess
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
    if not args.all_hubs and not args.hubs:
        print("Error: specify --hubs IATA1,IATA2 or --all-hubs", file=sys.stderr)
        sys.exit(2)
    from am4.utils.db import init

    init()
    cfg = _config_from_extract_args(args)
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
    os.environ["AM4_ROUTEMINE_DB"] = str(Path(args.db).resolve())
    root = Path(__file__).resolve().parent
    app = root / "dashboard" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.port",
        str(int(args.port)),
        "--browser.gatherUsageStats",
        "false",
    ]
    raise SystemExit(subprocess.call(cmd))


def main() -> None:
    parser = argparse.ArgumentParser(description="AM4 RouteMine — bulk route data extractor")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="Run bulk extraction")
    ex.add_argument("--hubs", type=str, help="Comma-separated IATA codes (e.g. KHI,DXB)")
    ex.add_argument("--all-hubs", action="store_true", help="Use every airport as a hub")
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

    dash = sub.add_parser("dashboard", help="Launch Streamlit dashboard")
    dash.add_argument("--db", type=str, default="am4_data.db")
    dash.add_argument("--port", type=int, default=8501)
    dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
