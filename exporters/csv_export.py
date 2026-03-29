"""Export database tables to CSV files."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

TABLES = ("aircraft", "airports", "route_demands", "route_aircraft")


def export_csv(db_path: str, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for name in TABLES:
            cur = conn.execute(f"SELECT * FROM {name}")
            rows = cur.fetchall()
            if not rows:
                path = out / f"{name}.csv"
                path.write_text("", encoding="utf-8")
                continue
            cols = rows[0].keys()
            path = out / f"{name}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow([r[c] for c in cols])
        cur = conn.execute("SELECT * FROM v_best_routes")
        rows = cur.fetchall()
        if rows:
            cols = rows[0].keys()
            path = out / "v_best_routes.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow([r[c] for c in cols])
    finally:
        conn.close()
