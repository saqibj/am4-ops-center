"""Extraction run records and per-run route snapshots for delta views."""

from __future__ import annotations

import sqlite3
from typing import Any

from config import UserConfig


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _route_aircraft_has_column(conn: sqlite3.Connection, col: str) -> bool:
    cur = conn.execute("PRAGMA table_info(route_aircraft)")
    return any(row[1] == col for row in cur.fetchall())


def ensure_extraction_runs_schema(conn: sqlite3.Connection) -> None:
    """Create extraction_runs, route_aircraft_snapshot, and route_aircraft.run_id if missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            scope TEXT NOT NULL DEFAULT 'hubs',
            hubs TEXT,
            aircraft_count INTEGER,
            route_count INTEGER,
            snapshot_count INTEGER,
            fuel_price REAL,
            co2_price REAL,
            status TEXT NOT NULL DEFAULT 'ok',
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS route_aircraft_snapshot (
            run_id INTEGER NOT NULL REFERENCES extraction_runs(id) ON DELETE CASCADE,
            origin_id INTEGER NOT NULL,
            dest_id INTEGER NOT NULL,
            aircraft_id INTEGER NOT NULL,
            profit_per_ac_day REAL,
            is_valid INTEGER,
            income REAL,
            PRIMARY KEY (run_id, origin_id, dest_id, aircraft_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ras_run ON route_aircraft_snapshot(run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ras_origin ON route_aircraft_snapshot(origin_id)"
    )
    if _table_exists(conn, "route_aircraft") and not _route_aircraft_has_column(
        conn, "run_id"
    ):
        conn.execute("ALTER TABLE route_aircraft ADD COLUMN run_id INTEGER REFERENCES extraction_runs(id)")
    conn.commit()


def start_extraction_run(
    conn: sqlite3.Connection,
    cfg: UserConfig,
    *,
    scope: str,
    hubs_csv: str,
) -> int:
    ensure_extraction_runs_schema(conn)
    conn.execute(
        """
        INSERT INTO extraction_runs (scope, hubs, fuel_price, co2_price, status)
        VALUES (?, ?, ?, ?, 'ok')
        """,
        (
            scope,
            hubs_csv,
            float(cfg.fuel_price),
            float(cfg.co2_price),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
    return int(row["id"])


def mark_extraction_run_failed(
    conn: sqlite3.Connection, run_id: int, message: str
) -> None:
    msg = (message or "")[:2000]
    conn.execute(
        """
        UPDATE extraction_runs
        SET finished_at = datetime('now'),
            status = 'error',
            notes = ?
        WHERE id = ?
        """,
        (msg, run_id),
    )
    conn.commit()


def finish_extraction_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    aircraft_count: int,
    route_count: int,
    snapshot_count: int,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE extraction_runs
        SET finished_at = datetime('now'),
            aircraft_count = ?,
            route_count = ?,
            snapshot_count = ?,
            notes = COALESCE(?, notes),
            status = 'ok'
        WHERE id = ?
        """,
        (aircraft_count, route_count, snapshot_count, notes, run_id),
    )
    conn.commit()


def insert_snapshots_for_run(
    conn: sqlite3.Connection,
    run_id: int,
    origin_ids: list[int] | None,
) -> int:
    """Replace snapshot rows for this run from current route_aircraft. Returns row count."""
    ensure_extraction_runs_schema(conn)
    conn.execute(
        "DELETE FROM route_aircraft_snapshot WHERE run_id = ?",
        (run_id,),
    )
    if origin_ids is None:
        conn.execute(
            """
            INSERT INTO route_aircraft_snapshot (
                run_id, origin_id, dest_id, aircraft_id,
                profit_per_ac_day, is_valid, income
            )
            SELECT ?, origin_id, dest_id, aircraft_id,
                   profit_per_ac_day, is_valid, income
            FROM route_aircraft
            """,
            (run_id,),
        )
    elif origin_ids:
        placeholders = ",".join("?" * len(origin_ids))
        conn.execute(
            f"""
            INSERT INTO route_aircraft_snapshot (
                run_id, origin_id, dest_id, aircraft_id,
                profit_per_ac_day, is_valid, income
            )
            SELECT ?, origin_id, dest_id, aircraft_id,
                   profit_per_ac_day, is_valid, income
            FROM route_aircraft
            WHERE origin_id IN ({placeholders})
            """,
            (run_id, *origin_ids),
        )
    conn.commit()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM route_aircraft_snapshot WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return int(row["c"] if row else 0)


def list_completed_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    ensure_extraction_runs_schema(conn)
    cur = conn.execute(
        """
        SELECT id, started_at, finished_at, scope, hubs, aircraft_count, route_count,
               snapshot_count, fuel_price, co2_price, status, notes
        FROM extraction_runs
        WHERE status = 'ok' AND finished_at IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]
