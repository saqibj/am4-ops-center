"""Tests for per-aircraft CI schema and DAO updates."""

import sqlite3
import pytest

from database.schema import create_schema, get_connection, _migrate_my_fleet_ci

def test_fresh_db_has_ci_default_200(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')")
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 10)")
    conn.commit()

    row = conn.execute("SELECT ci FROM my_fleet WHERE aircraft_id = 1").fetchone()
    assert row is not None
    assert int(row["ci"]) == 200
    conn.close()

def test_insert_with_explicit_ci(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')")
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity, ci) VALUES (1, 10, 150)")
    conn.commit()

    row = conn.execute("SELECT ci FROM my_fleet WHERE aircraft_id = 1").fetchone()
    assert row is not None
    assert int(row["ci"]) == 150
    conn.close()

def test_ci_check_constraint_rejects_invalid(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')")
    
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO my_fleet (aircraft_id, quantity, ci) VALUES (1, 10, 201)")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO my_fleet (aircraft_id, quantity, ci) VALUES (1, 10, -1)")
        
    conn.close()

def test_migrate_existing_db_adds_ci(tmp_path) -> None:
    db = tmp_path / "fleet_ci.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE my_fleet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aircraft_id INTEGER NOT NULL UNIQUE,
            quantity INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 10)")
    conn.commit()

    _migrate_my_fleet_ci(conn)
    _migrate_my_fleet_ci(conn)  # Idempotency

    row = conn.execute("SELECT ci FROM my_fleet WHERE aircraft_id = 1").fetchone()
    assert row is not None
    assert int(row["ci"]) == 200
    conn.close()
