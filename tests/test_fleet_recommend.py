"""fleet_recommend_rows breakeven: best-route vs average across routes."""

from __future__ import annotations

from commands.fleet_recommend import fleet_recommend_rows
from database.schema import create_schema, get_connection


def test_days_to_breakeven_best_le_avg_when_spread(tmp_path) -> None:
    db = tmp_path / "rec.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'AAA'), (3, 'BBB')")
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type, cost) VALUES (1, 't1', 'T1', 'PAX', 1000000)"
    )
    conn.execute(
        "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, profit_per_ac_day, is_valid) "
        "VALUES (1, 2, 1, 1000.0, 1)"
    )
    conn.execute(
        "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, profit_per_ac_day, is_valid) "
        "VALUES (1, 3, 1, 100.0, 1)"
    )
    conn.commit()
    rows, err = fleet_recommend_rows(conn, "KHI", 10_000_000, 10)
    conn.close()
    assert err is None
    assert len(rows) == 1
    r = rows[0]
    assert r["days_to_breakeven"] == r["days_to_breakeven_best"]
    assert r["days_to_breakeven_best"] is not None
    assert r["days_to_breakeven_avg"] is not None
    assert r["days_to_breakeven_best"] <= r["days_to_breakeven_avg"]


def test_days_to_breakeven_best_equals_avg_single_route(tmp_path) -> None:
    db = tmp_path / "rec2.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'AAA')")
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type, cost) VALUES (1, 't1', 'T1', 'PAX', 500000)"
    )
    conn.execute(
        "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, profit_per_ac_day, is_valid) "
        "VALUES (1, 2, 1, 250.0, 1)"
    )
    conn.commit()
    rows, err = fleet_recommend_rows(conn, "KHI", 10_000_000, 10)
    conn.close()
    assert err is None
    assert len(rows) == 1
    r = rows[0]
    assert r["days_to_breakeven_best"] == r["days_to_breakeven_avg"]
