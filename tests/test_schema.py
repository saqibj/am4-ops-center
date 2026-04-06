"""Schema unique constraints and migration."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from database.schema import create_schema, get_connection, migrate_add_unique_constraints
from extractors.routes import ROUTE_INSERT_SQL


def _base_route_row(**overrides: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "origin_id": 1,
        "dest_id": 2,
        "aircraft_id": 1,
        "distance_km": 100.0,
        "config_y": 180,
        "config_j": 0,
        "config_f": 0,
        "config_algorithm": "",
        "ticket_y": 0.0,
        "ticket_j": 0.0,
        "ticket_f": 0.0,
        "income": 0.0,
        "fuel_cost": 0.0,
        "co2_cost": 0.0,
        "repair_cost": 0.0,
        "acheck_cost": 0.0,
        "profit_per_trip": 0.0,
        "flight_time_hrs": 1.0,
        "trips_per_day": 1,
        "num_aircraft": 1,
        "profit_per_ac_day": 0.0,
        "income_per_ac_day": 0.0,
        "contribution": 0.0,
        "needs_stopover": 0,
        "stopover_iata": None,
        "total_distance": 100.0,
        "ci": 100,
        "warnings": "[]",
        "is_valid": 1,
        "game_mode": "easy",
    }
    r.update(overrides)
    return r


def test_route_aircraft_unique_constraint_raw_insert(tmp_path) -> None:
    db = tmp_path / "test.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.commit()
    conn.execute("INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id) VALUES (1, 2, 1)")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id) VALUES (1, 2, 1)")
    conn.close()


def test_route_upsert_updates_single_row(tmp_path) -> None:
    db = tmp_path / "test.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.commit()
    conn.execute(ROUTE_INSERT_SQL, _base_route_row(distance_km=50.0))
    conn.execute(ROUTE_INSERT_SQL, _base_route_row(distance_km=999.0))
    conn.commit()
    row = conn.execute(
        "SELECT distance_km FROM route_aircraft WHERE origin_id=1 AND dest_id=2 AND aircraft_id=1"
    ).fetchone()
    assert row is not None
    assert float(row[0]) == 999.0
    n = conn.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0]
    assert n == 1
    conn.close()


def test_migrate_idempotent_on_fresh_schema(tmp_path) -> None:
    db = tmp_path / "test.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.close()
    c2 = get_connection(db)
    migrate_add_unique_constraints(c2)
    c2.close()
    c3 = get_connection(db)
    migrate_add_unique_constraints(c3)
    c3.close()
    c4 = get_connection(db)
    row = c4.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='route_aircraft'"
    ).fetchone()
    assert row and "UNIQUE(origin_id, dest_id, aircraft_id)" in row[0]
    c4.close()
