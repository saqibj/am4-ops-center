"""Bearer token required on mutating /api/* POST (SEC-01 / SEC-06)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dbm
from dashboard.server import app
from database.schema import create_schema, get_connection


@pytest.fixture
def fleet_row_db(tmp_path, monkeypatch):
    db_path = tmp_path / "auth_fleet.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute("INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, 10)")
    conn.commit()
    row = conn.execute("SELECT id FROM my_fleet LIMIT 1").fetchone()
    assert row is not None
    fid = int(row[0])
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    return fid


def test_post_without_authorization_returns_401(fleet_row_db) -> None:
    client = TestClient(app)
    fid = fleet_row_db
    r = client.post(f"/api/fleet/{fid}/buy", data={"add_count": 1})
    assert r.status_code == 401
    assert "detail" in r.json()


def test_post_with_valid_bearer_succeeds(fleet_row_db, auth_headers) -> None:
    client = TestClient(app)
    fid = fleet_row_db
    r = client.post(
        f"/api/fleet/{fid}/buy",
        data={"add_count": 1},
        headers=auth_headers,
    )
    assert r.status_code == 200


@pytest.fixture
def saved_filters_db(tmp_path, monkeypatch):
    db_path = tmp_path / "saved_filters.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    return db_path


def test_saved_filters_save_requires_auth(saved_filters_db) -> None:
    client = TestClient(app)
    r = client.post(
        "/api/saved-filters/save",
        data={
            "page": "buy-next",
            "name": "preset-a",
            "params_json": "hub=DXB&top_n=5",
        },
    )
    assert r.status_code == 401


def test_saved_filters_save_roundtrip(saved_filters_db, auth_headers) -> None:
    client = TestClient(app)
    r = client.post(
        "/api/saved-filters/save",
        data={
            "page": "buy-next",
            "name": "preset-a",
            "params_json": "hub=DXB&top_n=5",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert "sf-wrap-buy-next" in r.text
    assert "preset-a" in r.text
    conn = get_connection(saved_filters_db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM saved_filters").fetchone()[0]
        assert n == 1
        row = conn.execute(
            "SELECT page, name, params_json FROM saved_filters LIMIT 1"
        ).fetchone()
        assert row[0] == "buy-next"
        assert row[1] == "preset-a"
        assert "DXB" in row[2]
    finally:
        conn.close()


def test_saved_filters_duplicate_name_returns_message(
    saved_filters_db, auth_headers
) -> None:
    client = TestClient(app)
    body = {
        "page": "buy-next",
        "name": "dup",
        "params_json": "top_n=3",
    }
    assert client.post(
        "/api/saved-filters/save", data=body, headers=auth_headers
    ).status_code == 200
    r2 = client.post(
        "/api/saved-filters/save", data=body, headers=auth_headers
    )
    assert r2.status_code == 200
    assert "already exists" in r2.text
