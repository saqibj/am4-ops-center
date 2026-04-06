"""Atomic fleet buy/sell (no read-then-write race on quantity)."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dbm
from database.schema import create_schema, get_connection
from dashboard.server import app


@pytest.fixture
def fleet_test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "fleet.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 10)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    return db_path


def _fleet_id(client: TestClient) -> int:
    r = client.get("/api/fleet/json")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    return int(data[0]["id"])


def test_fleet_buy_atomic_updates_quantity(fleet_test_db, auth_headers) -> None:
    client = TestClient(app)
    fid = _fleet_id(client)
    r = client.post(
        f"/api/fleet/{fid}/buy",
        data={"add_count": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert client.get("/api/fleet/json").json()[0]["quantity"] == 15


def test_fleet_concurrent_buys_no_lost_updates(fleet_test_db, auth_headers) -> None:
    client = TestClient(app)
    fid = _fleet_id(client)
    errors: list[str] = []
    lock = threading.Lock()

    def buy() -> None:
        try:
            resp = client.post(
                f"/api/fleet/{fid}/buy",
                data={"add_count": 5},
                headers=auth_headers,
            )
            if resp.status_code != 200:
                with lock:
                    errors.append(f"status {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(str(exc))

    threads = [threading.Thread(target=buy) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert client.get("/api/fleet/json").json()[0]["quantity"] == 30


def test_fleet_sell_respects_assigned_under_transaction(fleet_test_db, auth_headers) -> None:
    conn = get_connection(fleet_test_db)
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.execute(
        "INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned) "
        "VALUES (1, 2, 1, 3)"
    )
    conn.commit()
    conn.close()

    client = TestClient(app)
    fid = _fleet_id(client)
    r = client.post(
        f"/api/fleet/{fid}/sell",
        data={"sell_count": 8},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert "Only 7 unassigned" in r.text
    assert client.get("/api/fleet/json").json()[0]["quantity"] == 10

    r2 = client.post(
        f"/api/fleet/{fid}/sell",
        data={"sell_count": 7},
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert client.get("/api/fleet/json").json()[0]["quantity"] == 3
