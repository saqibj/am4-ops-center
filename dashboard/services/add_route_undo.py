"""Persisted undo window and recent-adds log for ``my_routes`` rows (SQLite)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dashboard.db import fetch_all, fetch_one

_MIGRATION_SQL = (
    Path(__file__).resolve().parent.parent
    / "db"
    / "migrations"
    / "003_add_route_add_undos.sql"
).read_text(encoding="utf-8")

_TRIM_KEEP = 20


def ensure_route_add_undos_schema(conn: sqlite3.Connection) -> None:
    """Create ``route_add_undos`` if missing (idempotent)."""
    conn.executescript(_MIGRATION_SQL)
    conn.execute("PRAGMA foreign_keys = ON")


def _trim_old_undo_rows(conn: sqlite3.Connection) -> None:
    """Keep only the newest ``_TRIM_KEEP`` rows by ``created_at`` (SQLite ``rowid`` tie-break)."""
    conn.execute(
        """
        DELETE FROM route_add_undos
        WHERE rowid NOT IN (
            SELECT rowid FROM route_add_undos
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
        )
        """,
        (_TRIM_KEEP,),
    )


def create_undo_token(conn: sqlite3.Connection, route_id: int, fleet_id: int | None) -> str:
    """Insert undo row with ~60s expiry; trim log to the last ``_TRIM_KEEP`` rows.

    Call :func:`ensure_route_add_undos_schema` on this connection **before**
    ``BEGIN`` — DDL must not run inside an open transaction.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    token = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO route_add_undos (token, route_id, fleet_id, expires_at)
        VALUES (?, ?, ?, datetime('now', '+60 seconds'))
        """,
        (token, int(route_id), fleet_id),
    )
    _trim_old_undo_rows(conn)
    return token


def _ago_label(created_at: str | None) -> str:
    if not created_at:
        return "—"
    raw = str(created_at).strip()
    try:
        if len(raw) >= 19:
            dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return raw
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sec = max(0, int((now - dt).total_seconds()))
    if sec < 60:
        return f"{sec}s ago"
    if sec < 3600:
        return f"{sec // 60}m ago"
    if sec < 86400:
        return f"{sec // 3600}h ago"
    return f"{sec // 86400}d ago"


def list_recent_adds(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    """Recent add log rows that still have a ``my_routes`` row, newest first."""
    ensure_route_add_undos_schema(conn)
    rows = fetch_all(
        conn,
        """
        SELECT u.token, u.route_id, u.fleet_id, u.created_at,
               mr.id AS mr_id, mr.aircraft_id,
               ho.iata AS origin_iata, hd.iata AS dest_iata,
               ac.shortname AS aircraft_short
        FROM route_add_undos u
        JOIN my_routes mr ON mr.id = u.route_id
        JOIN airports ho ON ho.id = mr.origin_id
        JOIN airports hd ON hd.id = mr.dest_id
        JOIN aircraft ac ON ac.id = mr.aircraft_id
        ORDER BY datetime(u.created_at) DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    out: list[dict] = []
    for r in rows:
        route_id = int(r["mr_id"])
        aircraft_id = int(r["aircraft_id"])
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
        fleet_id_raw = r.get("fleet_id")
        fleet_id = int(fleet_id_raw) if fleet_id_raw is not None else None
        fleet_qty: int | None = None
        if fleet_id is not None:
            fq = fetch_one(
                conn, "SELECT quantity FROM my_fleet WHERE id = ?", (fleet_id,)
            )
            fleet_qty = int(fq["quantity"]) if fq else None
        fleet_safe_to_remove = fleet_id is not None and other_n == 0
        out.append(
            {
                "token": str(r["token"]),
                "route_id": route_id,
                "origin_iata": str(r["origin_iata"] or "").strip().upper(),
                "dest_iata": str(r["dest_iata"] or "").strip().upper(),
                "aircraft_short": str(r["aircraft_short"] or "").strip(),
                "created_at": str(r["created_at"] or ""),
                "fleet_id": fleet_id,
                "fleet_qty": fleet_qty,
                "fleet_safe_to_remove": fleet_safe_to_remove,
                "ago_label": _ago_label(str(r["created_at"] or "")),
            }
        )
    return out


def get_recent_add_row(conn: sqlite3.Connection, token: str) -> dict | None:
    """Single recent-add row for HTMX row / confirm fragments (or ``None``)."""
    ensure_route_add_undos_schema(conn)
    rows = list_recent_adds(conn, limit=500)
    for row in rows:
        if row["token"] == token:
            return row
    return None


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


def delete_recent_add(
    conn: sqlite3.Connection, token: str, remove_fleet: bool
) -> dict | None:
    """Post–undo-window delete: remove route and log row; optional fleet if safe.

    ``remove_fleet`` is honored only when ``fleet_safe_to_remove`` is true server-side.
    Returns ``None`` if the token is unknown or already consumed.
    On success returns
    ``{"route_id", "fleet_id", "origin", "dest", "fleet_removed": bool}``.
    """
    ensure_route_add_undos_schema(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        ur = fetch_one(
            conn,
            "SELECT token, route_id, fleet_id FROM route_add_undos WHERE token = ?",
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
        fleet_safe = fleet_id is not None and other_n == 0
        delete_fleet = bool(remove_fleet) and fleet_safe and fleet_id is not None
        fleet_removed = False

        if delete_fleet:
            mf = fetch_one(conn, "SELECT id, aircraft_id FROM my_fleet WHERE id = ?", (fleet_id,))
            if mf and int(mf["aircraft_id"]) == aircraft_id:
                conn.execute("DELETE FROM my_fleet WHERE id = ?", (fleet_id,))
                fleet_removed = True

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
            "route_id": route_id,
            "fleet_id": fleet_id,
            "origin": origin_iata,
            "dest": dest_iata,
            "fleet_removed": fleet_removed,
        }
    except Exception:
        conn.rollback()
        raise
