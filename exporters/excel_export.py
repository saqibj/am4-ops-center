"""Export database tables to a multi-sheet Excel workbook."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

TABLES = ("aircraft", "airports", "route_demands", "route_aircraft")


def export_excel(db_path: str, output_dir: str | Path, filename: str = "am4_ops_center.xlsx") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / filename
    conn = sqlite3.connect(db_path)
    try:
        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            for name in TABLES:
                df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
                df.to_excel(writer, sheet_name=name[:31], index=False)
            dfv = pd.read_sql_query("SELECT * FROM v_best_routes", conn)
            dfv.to_excel(writer, sheet_name="v_best_routes"[:31], index=False)
    finally:
        conn.close()
