"""My Routes inventory: route_type filter and VIP-adjusted profit."""

from __future__ import annotations

import dashboard.db as dbm
from database.schema import create_schema, get_connection
from fastapi.testclient import TestClient

from dashboard.server import app


def test_inventory_filter_and_type_column(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "mr_inv.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.executescript(
        """
        INSERT INTO airports (id, iata, name) VALUES (1, 'AAA', 'A'), (2, 'BBB', 'B');
        INSERT INTO aircraft (id, shortname, name, type) VALUES (10, 'b738', 'Boeing', 'PAX');
        INSERT INTO aircraft (id, shortname, name, type) VALUES (11, 'b739', 'Boeing2', 'PAX');
        INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, route_type, notes)
        VALUES (1, 2, 10, 2, 'pax', NULL);
        INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, route_type, notes)
        VALUES (1, 2, 11, 1, 'vip', NULL);
        INSERT INTO route_aircraft (
            origin_id, dest_id, aircraft_id, distance_km,
            config_y, config_j, config_f,
            profit_per_trip, trips_per_day, profit_per_ac_day, income,
            is_valid
        ) VALUES (
            1, 2, 10, 1000.0,
            180, 12, 0,
            50000.0, 4, 200000.0, 200000.0,
            1
        );
        INSERT INTO route_aircraft (
            origin_id, dest_id, aircraft_id, distance_km,
            config_y, config_j, config_f,
            profit_per_trip, trips_per_day, profit_per_ac_day, income,
            is_valid
        ) VALUES (
            1, 2, 11, 1000.0,
            180, 12, 0,
            50000.0, 4, 200000.0, 200000.0,
            1
        );
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)

    r_all = client.get("/api/routes/inventory")
    assert r_all.status_code == 200
    assert "Type" in r_all.text
    assert "b738" in r_all.text and "b739" in r_all.text

    r_pax = client.get("/api/routes/inventory", params={"route_type": "pax"})
    assert r_pax.status_code == 200
    assert "b738" in r_pax.text
    assert "b739" not in r_pax.text
    assert "PAX" in r_pax.text

    r_vip = client.get("/api/routes/inventory", params={"route_type": "vip"})
    assert r_vip.status_code == 200
    assert "b739" in r_vip.text
    assert "b738" not in r_vip.text
    assert "VIP" in r_vip.text

    r_sum = client.get("/api/routes/summary")
    assert r_sum.status_code == 200
    assert "PAX:" in r_sum.text and "VIP:" in r_sum.text


def test_json_includes_route_type(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "mr_json.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.executescript(
        """
        INSERT INTO airports (id, iata) VALUES (1, 'X'), (2, 'Y');
        INSERT INTO aircraft (id, shortname, name, type) VALUES (5, 'a320', 'A', 'PAX');
        INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, route_type)
        VALUES (1, 2, 5, 1, 'cargo');
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    data = client.get("/api/routes/json").json()
    assert len(data) == 1
    assert data[0]["route_type"] == "cargo"
