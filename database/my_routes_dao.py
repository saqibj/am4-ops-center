"""``my_routes`` writes and ``route_type`` validation."""

from __future__ import annotations

import sqlite3
from typing import Literal

ALLOWED_ROUTE_TYPES = frozenset({"pax", "vip", "cargo", "charter"})

ImportMode = Literal["replace", "merge"]


def normalize_route_type(value: str | None) -> str:
    """Return a stored route type, defaulting to ``pax``.

    Raises:
        ValueError: if ``value`` is non-empty and not an allowed type.
    """
    if value is None:
        return "pax"
    s = str(value).strip().lower()
    if s == "":
        return "pax"
    if s not in ALLOWED_ROUTE_TYPES:
        raise ValueError(
            f"Invalid route_type {value!r}; expected one of {sorted(ALLOWED_ROUTE_TYPES)}"
        )
    return s


def upsert_my_route_from_csv_import(
    conn: sqlite3.Connection,
    *,
    origin_id: int,
    dest_id: int,
    aircraft_id: int,
    num_assigned: int,
    notes: str | None,
    mode: ImportMode,
    route_type: str | None = None,
) -> None:
    """Insert or merge a ``my_routes`` row (CLI CSV import). Defaults ``route_type`` to ``pax``."""
    rt = normalize_route_type(route_type)
    if mode == "replace":
        conn.execute(
            """
            INSERT INTO my_routes (
                origin_id, dest_id, aircraft_id, num_assigned, notes, route_type, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                num_assigned = excluded.num_assigned,
                notes = COALESCE(excluded.notes, my_routes.notes),
                route_type = excluded.route_type,
                updated_at = datetime('now')
            """,
            (origin_id, dest_id, aircraft_id, num_assigned, notes, rt),
        )
    else:
        conn.execute(
            """
            INSERT INTO my_routes (
                origin_id, dest_id, aircraft_id, num_assigned, notes, route_type, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                num_assigned = MIN(999, my_routes.num_assigned + excluded.num_assigned),
                notes = CASE
                    WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                    THEN excluded.notes
                    ELSE my_routes.notes
                END,
                route_type = excluded.route_type,
                updated_at = datetime('now')
            """,
            (origin_id, dest_id, aircraft_id, num_assigned, notes, rt),
        )
