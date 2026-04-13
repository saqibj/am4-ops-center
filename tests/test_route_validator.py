"""Tests for app.services.route_validator.validate_route."""

from __future__ import annotations

from app.services.route_validator import validate_route
from database.schema import create_schema, get_connection
from database.settings_dao import set_game_mode


def _route_aircraft_row(
    conn,
    *,
    oid: int,
    did: int,
    aid: int,
    distance_km: float,
    needs_stopover: int,
    stopover_iata: str | None,
    is_valid: int,
) -> None:
    conn.execute(
        """
        INSERT INTO route_aircraft (
            origin_id, dest_id, aircraft_id, distance_km,
            config_y, config_j, config_f, config_algorithm,
            ticket_y, ticket_j, ticket_f,
            income, fuel_cost, co2_cost, repair_cost, acheck_cost,
            profit_per_trip, flight_time_hrs, trips_per_day, num_aircraft,
            profit_per_ac_day, income_per_ac_day, contribution,
            needs_stopover, stopover_iata, total_distance,
            ci, warnings, is_valid, game_mode, fuel_price, co2_price
        ) VALUES (
            ?, ?, ?, ?,
            150, 20, 10, '',
            0, 0, 0,
            0, 0, 0, 0, 0,
            0, 1, 1, 1,
            100, 0, 0,
            ?, ?, ?,
            100, '[]', ?, 'easy', 700, 120
        )
        """,
        (
            oid,
            did,
            aid,
            distance_km,
            needs_stopover,
            stopover_iata,
            distance_km + 200,
            is_valid,
        ),
    )


def test_validate_range_below_no_valid_extraction(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 4000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 1000, 1500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 8000, 50, 0, 0)"
    )
    conn.commit()

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert r["errors"]
    assert any("no valid extraction row" in e for e in r["errors"])
    assert not r["stopover_required"]
    conn.close()


def test_validate_range_below_valid_stopover(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 4000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 1000, 1500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 9000, 50, 0, 0)"
    )
    _route_aircraft_row(
        conn,
        oid=1,
        did=2,
        aid=1,
        distance_km=9000,
        needs_stopover=1,
        stopover_iata="ZZZ",
        is_valid=1,
    )
    conn.commit()

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert not r["errors"]
    assert r["stopover_required"]
    assert r["stopover_hint"] and "ZZZ" in r["stopover_hint"]
    conn.close()


def test_validate_range_below_extraction_valid_no_stopover(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 4000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 1000, 1500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 9000, 50, 0, 0)"
    )
    _route_aircraft_row(
        conn,
        oid=1,
        did=2,
        aid=1,
        distance_km=9000,
        needs_stopover=0,
        stopover_iata=None,
        is_valid=1,
    )
    conn.commit()

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert r["errors"]
    assert any("does not show a valid stopover" in e for e in r["errors"])
    conn.close()


def test_validate_runway_exceeds_hub(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 2000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 10000, 3500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 1000, 50, 0, 0)"
    )
    conn.commit()
    set_game_mode(conn, "realism")

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert r["errors"]
    assert any("hub runway" in e.lower() for e in r["errors"])
    conn.close()


def test_validate_runway_skipped_in_easy_mode(tmp_path) -> None:
    """Easy game mode does not enforce hub/dest runway length vs aircraft requirement."""
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 2000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 10000, 3500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 1000, 50, 0, 0)"
    )
    _route_aircraft_row(
        conn,
        oid=1,
        did=2,
        aid=1,
        distance_km=1000,
        needs_stopover=0,
        stopover_iata=None,
        is_valid=1,
    )
    conn.commit()
    set_game_mode(conn, "easy")

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert not r["errors"]
    conn.close()


def test_validate_runway_exceeds_dest_in_realism(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 4000, 0, 0), (2, 'BBB', 2000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 10000, 3500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 1000, 50, 0, 0)"
    )
    conn.commit()
    set_game_mode(conn, "realism")

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert r["errors"]
    assert any("destination runway" in e.lower() for e in r["errors"])
    conn.close()


def test_validate_duplicate_my_routes_warning_only(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 4000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 10000, 1500, 180)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 1000, 5, 0, 0)"
    )
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 1)"
    )
    conn.commit()

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert not r["errors"]
    assert r["warnings"]
    assert any("merges" in w.lower() for w in r["warnings"])
    conn.close()


def test_validate_demand_vs_seats_warning(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'AAA', 4000, 0, 0), (2, 'BBB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'ac', 'Test', 'PAX', 10000, 1500, 200)
        """
    )
    conn.execute(
        "INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f) "
        "VALUES (1, 2, 1000, 10, 0, 0)"
    )
    conn.commit()

    r = validate_route(conn, "AAA", "BBB", "ac")
    assert not r["errors"]
    assert any("demand" in w.lower() for w in r["warnings"])
    conn.close()
