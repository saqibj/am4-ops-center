"""Hub service: delete_hub and explorer hub SQL against real schema."""

from __future__ import annotations

from app.services.hubs import (
    SQL_EXPLORER_HUB_IATAS,
    delete_hub,
)
from database.schema import create_schema, get_connection


def test_delete_hub_clears_route_tables_and_my_hubs(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute(
        "INSERT INTO airports (id, iata, name, country) VALUES (1, 'AAA', 'A', 'X'), (2, 'BBB', 'B', 'Y')"
    )
    conn.commit()
    conn.execute("INSERT INTO my_hubs (airport_id, is_active, last_extract_status) VALUES (1, 1, 'ok')")
    conn.execute(
        "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, is_valid) VALUES (1, 2, 1, 1)"
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 100, 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
    )
    conn.commit()

    delete_hub(conn, 1)

    assert conn.execute("SELECT COUNT(*) AS n FROM my_hubs").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM route_aircraft").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM route_demands").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM my_routes").fetchone()["n"] == 0
    conn.close()


def test_delete_hub_removes_routes_where_airport_is_destination(tmp_path) -> None:
    db = tmp_path / "t2.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'AAA'), (2, 'BBB')")
    conn.commit()
    conn.execute("INSERT INTO my_hubs (airport_id, is_active, last_extract_status) VALUES (2, 1, 'ok')")
    conn.execute(
        "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, is_valid) VALUES (1, 2, 1, 1)"
    )
    conn.commit()

    delete_hub(conn, 2)

    assert conn.execute("SELECT COUNT(*) AS n FROM route_aircraft").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM my_hubs").fetchone()["n"] == 0
    conn.close()


def test_explorer_hub_sql_excludes_inactive_and_never_extracted(tmp_path) -> None:
    db = tmp_path / "t3.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'OK1'), (2, 'ZZ2')")
    conn.commit()
    conn.execute(
        "INSERT INTO my_hubs (airport_id, is_active, last_extract_status) VALUES (1, 1, 'ok')"
    )
    conn.execute(
        "INSERT INTO my_hubs (airport_id, is_active, last_extract_status) VALUES (2, 0, NULL)"
    )
    conn.commit()

    rows = conn.execute(SQL_EXPLORER_HUB_IATAS).fetchall()
    assert [r["iata"] for r in rows] == ["OK1"]

    conn.close()


def test_explorer_hub_sql_excludes_ok_status_without_active(tmp_path) -> None:
    db = tmp_path / "t4.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'X1')")
    conn.commit()
    conn.execute(
        "INSERT INTO my_hubs (airport_id, is_active, last_extract_status) VALUES (1, 0, 'ok')"
    )
    conn.commit()

    rows = conn.execute(SQL_EXPLORER_HUB_IATAS).fetchall()
    assert rows == []

    conn.close()
