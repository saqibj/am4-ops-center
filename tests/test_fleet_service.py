"""Tests for app.services.fleet_service (eligible aircraft and availability)."""

from __future__ import annotations

import pytest

from app.services.fleet_service import available_aircraft_at_hub, get_eligible_aircraft
from database.schema import create_schema, get_connection


def test_get_eligible_aircraft_filters_and_counts(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)

    # KHI: 3000m runway; DXB: 4000m
    conn.execute(
        "INSERT INTO airports (id, iata, rwy) VALUES (1, 'KHI', 3000), (2, 'DXB', 4000)"
    )
    conn.executemany(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (?, ?, ?, 'PAX', ?, ?, 180)
        """,
        [
            (1, "a1", "Fully assigned", 5000, 1500),
            (2, "a2", "Partially assigned", 5000, 1500),
            (3, "a3", "Free", 5000, 1500),
            (4, "a4", "Short range", 1000, 1500),
            (5, "a5", "Too much runway need", 8000, 3500),
        ],
    )
    conn.executemany(
        "INSERT INTO my_fleet (aircraft_id, quantity) VALUES (?, ?)",
        [(1, 5), (2, 5), (3, 3), (4, 2), (5, 1)],
    )
    # All assignments originate at KHI (hub)
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 5)"
    )
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 2, 2)"
    )
    conn.commit()

    rows = get_eligible_aircraft(conn, "KHI", "DXB", 5000.0)
    by_sn = {r["shortname"]: r for r in rows}

    assert "a1" not in by_sn  # fully assigned (fleet global)
    assert "a5" not in by_sn  # runway 3500 > KHI 3000

    assert by_sn["a2"]["available_count"] == 3
    assert by_sn["a2"]["current_route_count"] == 1
    assert by_sn["a2"]["eligible_direct"] is True
    assert by_sn["a2"]["eligible_with_stopover"] is False

    assert by_sn["a3"]["available_count"] == 3
    assert by_sn["a3"]["current_route_count"] == 0

    assert by_sn["a4"]["eligible_direct"] is False
    assert by_sn["a4"]["eligible_with_stopover"] is True
    assert by_sn["a4"]["stopover_hint"] is not None

    conn.close()


def test_available_aircraft_at_hub_uses_global_assignments(tmp_path) -> None:
    """Assignments at another hub consume the global fleet count; no \"free\" planes at DXB."""
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)

    conn.execute(
        "INSERT INTO airports (id, iata, rwy) VALUES (1, 'LHR', 4000), (2, 'DXB', 4000)"
    )
    a320_id = 322
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (?, 'A320', 'Airbus A320', 'PAX', 5000, 1500, 180)
        """,
        (a320_id,),
    )
    conn.execute(
        "INSERT INTO my_fleet (aircraft_id, quantity) VALUES (?, 2)",
        (a320_id,),
    )
    conn.execute(
        """
        INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned)
        VALUES (1, 2, ?, 2)
        """,
        (a320_id,),
    )
    conn.commit()

    assert available_aircraft_at_hub(conn, a320_id) == 0

    conn.close()


def test_get_eligible_aircraft_route_aircraft_stopover_hint(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO airports (id, iata, rwy) VALUES (1, 'KHI', 3000), (2, 'DXB', 4000)")
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'lr', 'Long route short range', 'PAX', 1000, 1500, 180)
        """
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 2)")
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
            1, 2, 1, 9000,
            150, 20, 10, '',
            0, 0, 0,
            0, 0, 0, 0, 0,
            0, 1, 1, 1,
            100, 0, 0,
            1, 'AUH', 9200,
            100, '[]', 1, 'easy', 700, 120
        )
        """
    )
    conn.commit()

    rows = get_eligible_aircraft(conn, "khi", "dxb", 5000.0)
    assert len(rows) == 1
    assert rows[0]["stopover_hint"] == "via AUH"
    assert rows[0]["config_summary"] == "Y150 J20 F10"
    conn.close()


def test_get_eligible_aircraft_unknown_iata(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO airports (id, iata, rwy) VALUES (1, 'KHI', 3000)")
    conn.commit()
    with pytest.raises(ValueError, match="Unknown destination"):
        get_eligible_aircraft(conn, "KHI", "XXX", 100.0)
    conn.close()
