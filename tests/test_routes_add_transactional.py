"""POST /api/routes/add transactional behavior (optional inline fleet)."""

from __future__ import annotations

import dashboard.db as dbm
from database.schema import create_schema, get_connection
from fastapi.testclient import TestClient

from dashboard.server import app


def _base_route_db(path) -> None:
    conn = get_connection(path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'KHI', 3000, 24.86, 67.00), (2, 'DXB', 4000, 25.25, 55.36)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'a1', 'Type one', 'PAX', 8000, 1500, 180)
        """
    )
    conn.execute(
        """
        INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f)
        VALUES (1, 2, 5000, 100, 10, 1)
        """
    )
    conn.commit()
    conn.close()


def test_routes_add_existing_fleet_happy_path(tmp_path, monkeypatch, auth_headers) -> None:
    db_path = tmp_path / "radd1.db"
    _base_route_db(db_path)
    conn = get_connection(db_path)
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 3)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.post(
        "/api/routes/add",
        data={
            "hub_iata": "KHI",
            "destination_iata": "DXB",
            "aircraft": "a1",
            "num_assigned": "1",
            "notes": "",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert 'data-routes-error="1"' not in r.text
    assert (
        "Added" in r.text
        or "Merged" in r.text
        or "route-add-flash-undo" in r.text
    )

    conn = get_connection(db_path)
    n = conn.execute("SELECT COUNT(*) FROM my_routes WHERE origin_id=1 AND dest_id=2 AND aircraft_id=1").fetchone()[0]
    conn.close()
    assert int(n) == 1


def test_routes_add_inline_fleet_and_route(tmp_path, monkeypatch, auth_headers) -> None:
    db_path = tmp_path / "radd2.db"
    _base_route_db(db_path)

    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.post(
        "/api/routes/add",
        data={
            "hub_iata": "KHI",
            "destination_iata": "DXB",
            "aircraft": "a1",
            "num_assigned": "1",
            "notes": "r",
            "inline_fleet_quantity": "2",
            "inline_fleet_notes": "fleet n",
            "route_config_y": "150",
            "route_config_j": "10",
            "route_config_f": "0",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert 'data-routes-error="1"' not in r.text
    assert "Added 2" in r.text and "fleet" in r.text.lower()
    assert "Awaiting extraction" in r.text or "extraction" in r.text.lower()

    conn = get_connection(db_path)
    q = conn.execute("SELECT quantity FROM my_fleet WHERE aircraft_id=1").fetchone()[0]
    n = conn.execute("SELECT num_assigned FROM my_routes WHERE origin_id=1 AND dest_id=2").fetchone()[0]
    conn.close()
    assert int(q) == 2
    assert int(n) == 1


def test_routes_add_inline_fleet_rollback_on_validation(tmp_path, monkeypatch, auth_headers) -> None:
    db_path = tmp_path / "radd3.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES (1, 'KHI', 3000, 0, 0), (2, 'DXB', 4000, 1, 1)"
    )
    conn.execute(
        """
        INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity)
        VALUES (1, 'shorty', 'Short', 'PAX', 1000, 1500, 180)
        """
    )
    conn.execute(
        """
        INSERT INTO route_demands (origin_id, dest_id, distance_km, demand_y, demand_j, demand_f)
        VALUES (1, 2, 8000, 50, 0, 0)
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.post(
        "/api/routes/add",
        data={
            "hub_iata": "KHI",
            "destination_iata": "DXB",
            "aircraft": "shorty",
            "num_assigned": "1",
            "inline_fleet_quantity": "1",
            "route_config_y": "150",
            "route_config_j": "10",
            "route_config_f": "0",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert 'data-routes-error="1"' in r.text

    conn = get_connection(db_path)
    mf = conn.execute("SELECT COUNT(*) FROM my_fleet WHERE aircraft_id=1").fetchone()[0]
    mr = conn.execute("SELECT COUNT(*) FROM my_routes").fetchone()[0]
    conn.close()
    assert int(mf) == 0
    assert int(mr) == 0


def test_routes_add_rejects_over_assign_at_hub(tmp_path, monkeypatch, auth_headers) -> None:
    db_path = tmp_path / "radd4.db"
    _base_route_db(db_path)
    conn = get_connection(db_path)
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.post(
        "/api/routes/add",
        data={
            "hub_iata": "KHI",
            "destination_iata": "DXB",
            "aircraft": "a1",
            "num_assigned": "5",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert 'data-routes-error="1"' in r.text
    assert "Only 1" in r.text

    conn = get_connection(db_path)
    mr = conn.execute("SELECT COUNT(*) FROM my_routes").fetchone()[0]
    conn.close()
    assert int(mr) == 0
