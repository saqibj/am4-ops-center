"""Regression: hub freshness SQL must not enumerate hubs from orphan route_aircraft rows."""

from __future__ import annotations

import sqlite3

from dashboard.db import _HUB_FRESHNESS_SQL, fetch_all
from database.schema import create_schema, get_connection


def test_hub_freshness_sql_excludes_deleted_hub_with_orphan_routes(tmp_path) -> None:
    """If my_hubs row is removed but route_aircraft rows remain, hub must not appear."""
    db = tmp_path / "ghost.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute(
        """
        INSERT INTO airports (id, iata, name) VALUES
            (10, 'STN', 'Stansted'),
            (11, 'LHR', 'Heathrow'),
            (12, 'JFK', 'JFK')
        """
    )
    conn.execute(
        """
        INSERT INTO my_hubs (airport_id, is_active, last_extract_status)
        VALUES (10, 1, 'ok'), (11, 1, 'ok')
        """
    )
    conn.execute(
        """
        INSERT INTO route_aircraft (
            origin_id, dest_id, aircraft_id, distance_km,
            config_y, config_j, config_f, config_algorithm,
            ticket_y, ticket_j, ticket_f, income,
            fuel_cost, co2_cost, repair_cost, acheck_cost,
            profit_per_trip, flight_time_hrs, trips_per_day, num_aircraft,
            profit_per_ac_day, income_per_ac_day, contribution,
            needs_stopover, stopover_iata, warnings, is_valid, game_mode,
            fuel_price, co2_price, extracted_at
        ) VALUES (
            10, 12, 1, 5000.0,
            180, 0, 0, '',
            0, 0, 0, 100000.0,
            0, 0, 0, 0,
            1000.0, 8.0, 1, 1,
            50000.0, 100000.0, 0.0,
            0, NULL, '[]', 1, 'easy',
            700.0, 120.0, '2025-01-01T00:00:00Z'
        ),
        (
            11, 12, 1, 5000.0,
            180, 0, 0, '',
            0, 0, 0, 100000.0,
            0, 0, 0, 0,
            1000.0, 8.0, 1, 1,
            50000.0, 100000.0, 0.0,
            0, NULL, '[]', 1, 'easy',
            700.0, 120.0, '2025-01-02T00:00:00Z'
        )
        """
    )
    conn.commit()

    rows_before = fetch_all(conn, _HUB_FRESHNESS_SQL)
    assert {"STN", "LHR"} <= {r["hub"] for r in rows_before}

    conn.execute("DELETE FROM my_hubs WHERE airport_id = 10")
    conn.commit()

    rows_after = fetch_all(conn, _HUB_FRESHNESS_SQL)
    hubs = {r["hub"] for r in rows_after}
    assert "STN" not in hubs
    assert "LHR" in hubs

    conn.close()
