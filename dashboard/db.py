"""SQLite access helpers (sync) for the dashboard."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import Request

DB_PATH = os.environ.get("AM4_ROUTEMINE_DB", "am4_data.db")


def get_db() -> sqlite3.Connection:
    p = Path(DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    from database.schema import ensure_route_aircraft_baseline_prices

    ensure_route_aircraft_baseline_prices(conn)
    return conn


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    cur = conn.execute(sql, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> dict | None:
    cur = conn.execute(sql, tuple(params))
    row = cur.fetchone()
    return dict(row) if row else None


def db_file_size_bytes() -> int | None:
    p = Path(DB_PATH)
    if not p.exists():
        return None
    return p.stat().st_size


def base_context(request: Request) -> dict:
    try:
        conn = get_db()
        try:
            row = fetch_one(
                conn,
                "SELECT COUNT(*) AS route_count FROM route_aircraft WHERE is_valid = 1",
            )
            rc = int(row["route_count"]) if row else 0
        finally:
            conn.close()
    except FileNotFoundError:
        rc = 0
    return {
        "request": request,
        "db_name": os.path.basename(DB_PATH),
        "route_count": rc,
    }
