"""``my_routes.route_type`` column, triggers, and DAO helpers."""

from __future__ import annotations

import sqlite3

import pytest

from database.my_routes_dao import normalize_route_type, upsert_my_route_from_csv_import
from database.schema import (
    _ensure_my_routes_route_type_triggers,
    _migrate_my_routes_route_type,
    create_schema,
    ensure_my_routes_inventory_schema,
    get_connection,
)


def test_normalize_route_type_defaults_and_validates() -> None:
    assert normalize_route_type(None) == "pax"
    assert normalize_route_type("") == "pax"
    assert normalize_route_type("VIP") == "vip"
    with pytest.raises(ValueError, match="Invalid route_type"):
        normalize_route_type("first")


def test_fresh_schema_has_route_type_and_triggers(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(my_routes)").fetchall()}
    assert "route_type" in cols
    trg = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' "
        "AND name='trg_my_routes_route_type_check' LIMIT 1"
    ).fetchone()
    assert trg is not None
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.commit()
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, route_type) "
        "VALUES (1, 2, 1, 1, 'vip')"
    )
    conn.commit()
    row = conn.execute("SELECT route_type FROM my_routes LIMIT 1").fetchone()
    assert row is not None and row[0] == "vip"
    with pytest.raises(sqlite3.Error):
        conn.execute(
            "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, route_type) "
            "VALUES (1, 2, 1, 2, 'nope')"
        )
    conn.close()


def test_migrate_my_routes_route_type_alter_table(tmp_path) -> None:
    db = tmp_path / "legacy.db"
    conn = get_connection(db)
    conn.executescript(
        """
        CREATE TABLE my_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin_id INTEGER NOT NULL,
            dest_id INTEGER NOT NULL,
            aircraft_id INTEGER NOT NULL,
            num_assigned INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            UNIQUE(origin_id, dest_id, aircraft_id)
        );
        """
    )
    conn.commit()
    assert _migrate_my_routes_route_type(conn) is True
    assert _migrate_my_routes_route_type(conn) is False
    _ensure_my_routes_route_type_triggers(conn)
    conn.commit()
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
    )
    conn.commit()
    assert conn.execute("SELECT route_type FROM my_routes").fetchone()[0] == "pax"
    conn.close()


def test_dao_upsert_persists_vip(tmp_path) -> None:
    db = tmp_path / "dao.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.commit()
    upsert_my_route_from_csv_import(
        conn,
        origin_id=1,
        dest_id=2,
        aircraft_id=1,
        num_assigned=2,
        notes=None,
        mode="replace",
        route_type="vip",
    )
    conn.commit()
    assert (
        conn.execute("SELECT route_type FROM my_routes").fetchone()[0] == "vip"
    )
    conn.close()


def test_ensure_my_routes_inventory_schema_idempotent(tmp_path) -> None:
    db = tmp_path / "inv.db"
    conn = get_connection(db)
    create_schema(conn)
    ensure_my_routes_inventory_schema(conn)
    ensure_my_routes_inventory_schema(conn)
    conn.close()
