"""Schema unique constraints and migration."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from config import UserConfig
from database.schema import (
    clear_route_tables,
    create_schema,
    derived_total_planes,
    get_connection,
    load_extract_config,
    migrate_add_unique_constraints,
    replace_master_tables,
    save_extract_config,
)
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
        "fuel_price": 700.0,
        "co2_price": 120.0,
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


class _ConnBoomOnFirstRouteDelete:
    """sqlite3.Connection.execute is not patchable on Python 3.14+; delegate with a hook."""

    def __init__(self, inner: sqlite3.Connection) -> None:
        self._inner = inner
        self._armed = True

    def execute(self, sql: str, parameters: Any = ()) -> sqlite3.Cursor:
        if "DELETE FROM route_aircraft" in sql and self._armed:
            self._armed = False
            raise sqlite3.OperationalError("simulated failure")
        return self._inner.execute(sql, parameters) if parameters else self._inner.execute(sql)

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self._inner.rollback()


def test_replace_master_tables_restores_fk_on_error(tmp_path) -> None:
    db = tmp_path / "fk.db"
    inner = get_connection(db)
    create_schema(inner)
    wrapped = _ConnBoomOnFirstRouteDelete(inner)

    with pytest.raises(sqlite3.OperationalError, match="simulated"):
        replace_master_tables(wrapped)  # type: ignore[arg-type]

    fk = inner.execute("PRAGMA foreign_keys").fetchone()
    assert fk is not None and int(fk[0]) == 1
    inner.close()


def test_replace_master_tables_clears_routes_then_masters(tmp_path) -> None:
    db = tmp_path / "masters.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.commit()
    conn.execute(ROUTE_INSERT_SQL, _base_route_row())
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 100.0, 1, 0, 0)"
    )
    conn.commit()
    replace_master_tables(conn)
    assert conn.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM route_demands").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM aircraft").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0] == 0
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk is not None and int(fk[0]) == 1
    conn.close()


def test_clear_route_tables_resets_route_aircraft_sequence(tmp_path) -> None:
    db = tmp_path / "seq.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.commit()
    conn.execute(ROUTE_INSERT_SQL, _base_route_row())
    conn.commit()
    max_before = conn.execute("SELECT MAX(id) FROM route_aircraft").fetchone()[0]
    assert max_before is not None
    clear_route_tables(conn)
    conn.execute(ROUTE_INSERT_SQL, _base_route_row())
    conn.commit()
    max_after = conn.execute("SELECT MAX(id) FROM route_aircraft").fetchone()[0]
    assert max_after is not None
    assert int(max_after) <= int(max_before)
    conn.close()


def test_save_load_extract_config_roundtrip(tmp_path) -> None:
    db = tmp_path / "meta.db"
    conn = get_connection(db)
    create_schema(conn)
    cfg = UserConfig(reputation=95.0, cost_index=180, total_planes_owned=42)
    save_extract_config(conn, cfg)
    conn.close()
    c2 = get_connection(db)
    got = load_extract_config(c2)
    c2.close()
    assert got is not None
    assert got.reputation == 95.0
    assert got.cost_index == 180
    assert got.total_planes_owned == 42


def test_user_config_extract_id_scan_defaults() -> None:
    c = UserConfig()
    assert c.aircraft_id_max == 1000
    assert c.airport_id_max == 8000


def test_save_load_extract_config_preserves_id_max(tmp_path) -> None:
    db = tmp_path / "meta_ids.db"
    conn = get_connection(db)
    create_schema(conn)
    cfg = UserConfig(aircraft_id_max=200, airport_id_max=5000)
    save_extract_config(conn, cfg)
    conn.close()
    c2 = get_connection(db)
    got = load_extract_config(c2)
    c2.close()
    assert got is not None
    assert got.aircraft_id_max == 200
    assert got.airport_id_max == 5000


def test_derived_total_planes_none_when_fleet_empty(tmp_path) -> None:
    db = tmp_path / "fleet.db"
    conn = get_connection(db)
    create_schema(conn)
    assert derived_total_planes(conn) is None
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 10)")
    conn.commit()
    assert derived_total_planes(conn) == 10
    conn.close()
