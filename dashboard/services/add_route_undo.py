"""Persisted undo window for newly added ``my_routes`` rows (SQLite)."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from dashboard.db import fetch_one

_MIGRATION_SQL = (Path(__file__).resolve().parent.parent / "db" / "migrations" / "003_add_route_add_undos.sql").read_text(
    encoding="utf-8"
)


def ensure_route_add_undos_schema(conn: sqlite3.Connection) -> None:
    """Create ``route_add_undos`` if missing (idempotent)."""
    conn.executescript(_MIGRATION_SQL)
    conn.execute("PRAGMA foreign_keys = ON")


def create_undo_token(conn: sqlite3.Connection, route_id: int, fleet_id: int | None) -> str:
    """Insert undo row with ~60s expiry; opportunistically delete expired rows.

    Call :func:`ensure_route_add_undos_schema` on this connection **before**
    ``BEGIN`` — DDL must not run inside an open transaction.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    token = str(uuid.uuid4())
    conn.execute("DELETE FROM route_add_undos WHERE expires_at < datetime('now')")
    conn.execute(
        """
        INSERT INTO route_add_undos (token, route_id, fleet_id, expires_at)
        VALUES (?, ?, ?, datetime('now', '+60 seconds'))
        """,
        (token, int(route_id), fleet_id),
    )
    return token


def consume_undo_token(conn: sqlite3.Connection, token: str) -> dict | None:
    """If token is valid and unexpired, delete route (+ optional fleet) and return IATA labels.

    Returns ``None`` when the token is missing, expired, already consumed, or the
    route row is already gone. On success returns
    ``{"origin": str, "dest": str, "route_id": int, "fleet_id": int | None}``.
    """
    ensure_route_add_undos_schema(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        ur = fetch_one(
            conn,
            """
            SELECT token, route_id, fleet_id, expires_at
            FROM route_add_undos
            WHERE token = ?
              AND expires_at > datetime('now')
            """,
            (token,),
        )
        if not ur:
            conn.rollback()
            return None

        route_id = int(ur["route_id"])
        fleet_id_raw = ur["fleet_id"]
        fleet_id = int(fleet_id_raw) if fleet_id_raw is not None else None

        mr = fetch_one(
            conn,
            """
            SELECT mr.id, mr.origin_id, mr.dest_id, mr.aircraft_id,
                   ho.iata AS origin_iata, hd.iata AS dest_iata
            FROM my_routes mr
            JOIN airports ho ON ho.id = mr.origin_id
            JOIN airports hd ON hd.id = mr.dest_id
            WHERE mr.id = ?
            """,
            (route_id,),
        )
        if not mr:
            conn.execute("DELETE FROM route_add_undos WHERE token = ?", (token,))
            conn.commit()
            return None

        origin_id = int(mr["origin_id"])
        dest_id = int(mr["dest_id"])
        aircraft_id = int(mr["aircraft_id"])
        origin_iata = str(mr["origin_iata"] or "").strip().upper()
        dest_iata = str(mr["dest_iata"] or "").strip().upper()

        others = fetch_one(
            conn,
            """
            SELECT COUNT(*) AS n
            FROM my_routes
            WHERE aircraft_id = ? AND id != ?
            """,
            (aircraft_id, route_id),
        )
        other_n = int(others["n"] or 0) if others else 0

        if fleet_id is not None and other_n == 0:
            mf = fetch_one(conn, "SELECT id, aircraft_id FROM my_fleet WHERE id = ?", (fleet_id,))
            if mf and int(mf["aircraft_id"]) == aircraft_id:
                conn.execute("DELETE FROM my_fleet WHERE id = ?", (fleet_id,))

        conn.execute(
            """
            DELETE FROM route_aircraft
            WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
            """,
            (origin_id, dest_id, aircraft_id),
        )
        conn.execute("DELETE FROM my_routes WHERE id = ?", (route_id,))
        conn.execute("DELETE FROM route_add_undos WHERE token = ?", (token,))
        conn.commit()
        return {
            "origin": origin_iata,
            "dest": dest_iata,
            "route_id": route_id,
            "fleet_id": fleet_id,
        }
    except Exception:
        conn.rollback()
        raise
