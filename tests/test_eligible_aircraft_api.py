"""GET /api/routes/eligible-aircraft (HTML + JSON)."""

from __future__ import annotations

import dashboard.db as dbm
from database.schema import create_schema, get_connection
from fastapi.testclient import TestClient

from dashboard.server import app


def _seed_db(path) -> None:
    conn = get_connection(path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'KHI', 3000, 24.86, 67.00), (2, 'DXB', 4000, 25.25, 55.36)"
    )
    conn.executemany(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (?, ?, ?, 'PAX', ?, ?, 180)
        """,
        [
            (1, "a1", "Fully assigned", 5000, 1500),
            (2, "a2", "Free bird", 5000, 1500),
        ],
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 5), (2, 3)")
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 5)"
    )
    conn.execute(
        """
        INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f)
        VALUES (1, 2, 5000, 100, 10, 1)
        """
    )
    conn.commit()
    conn.close()


def test_eligible_aircraft_json_lists_free_plane(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "elig.db"
    _seed_db(db_path)
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.get(
        "/api/routes/eligible-aircraft",
        params={"hub": "KHI", "dest": "DXB", "format": "json"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["hub"] == "KHI"
    assert data["dest"] == "DXB"
    assert data["distance_km"] == 5000.0
    sns = {a["shortname"] for a in data["aircraft"]}
    assert sns == {"a2"}
    assert data["empty_reason"] is None


def test_eligible_aircraft_html_contains_option_hints(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "elig2.db"
    _seed_db(db_path)
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.get(
        "/api/routes/eligible-aircraft",
        params={"hub": "KHI", "destination_iata": "DXB"},
        headers={"Accept": "text/html"},
    )
    assert r.status_code == 200
    body = r.text
    assert "a2" in body
    assert "Free bird" in body
    assert "5000 km" in body
    assert "available" in body


def test_eligible_aircraft_empty_reason_in_html(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "elig3.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy) VALUES (1, 'KHI', 3000), (2, 'DXB', 4000)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'only', 'Only type', 'PAX', 5000, 1500, 180)
        """
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 2)")
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 2)"
    )
    conn.execute(
        """
        INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f)
        VALUES (1, 2, 5000, 1, 0, 0)
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.get(
        "/api/routes/eligible-aircraft",
        params={"hub": "KHI", "dest": "DXB"},
        headers={"Accept": "text/html", "HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "data-empty-reason" in r.text
    assert "No eligible aircraft at KHI" in r.text
    assert "5,000 km" in r.text or "5000 km" in r.text


def test_eligible_aircraft_empty_html_inline_fleet_markup(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "elig_inline.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy) VALUES (1, 'KHI', 3000), (2, 'DXB', 4000)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity, cost)
        VALUES (1, 'only', 'Only type', 'PAX', 5000, 1500, 180, 123456789)
        """
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 2)")
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) VALUES (1, 2, 1, 2)"
    )
    conn.execute(
        """
        INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f)
        VALUES (1, 2, 5000, 1, 0, 0)
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.get(
        "/api/routes/eligible-aircraft",
        params={"hub": "KHI", "dest": "DXB"},
        headers={"Accept": "text/html"},
    )
    assert r.status_code == 200
    assert 'data-inline-fleet-entry="1"' in r.text
    assert "inline_fleet_quantity" in r.text
    assert 'form="add-route-main"' in r.text
    assert "/buy-next?" in r.text and "hub=KHI" in r.text


def test_eligible_aircraft_json_unknown_airport(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "elig4.db"
    _seed_db(db_path)
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.get(
        "/api/routes/eligible-aircraft",
        params={"hub": "KHI", "dest": "ZZZ", "format": "json"},
    )
    assert r.status_code == 422
    assert "error" in r.json()
