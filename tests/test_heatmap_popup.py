"""Heatmap Leaflet popups use DOM textContent (SEC-04)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dbm
from dashboard.server import app
from database.schema import create_schema, get_connection


@pytest.fixture
def heatmap_db_with_xss_name(tmp_path, monkeypatch):
    db_path = tmp_path / "heatmap_sec04.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, name, lat, lng) VALUES (1, 'KHI', 'Karachi', 24.9, 67.0)"
    )
    conn.execute(
        "INSERT INTO airports (id, iata, name, lat, lng) VALUES (2, 'DXB', "
        "'<img src=x onerror=alert(1)>XSS', 25.2, 55.3)"
    )
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')"
    )
    conn.execute(
        "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, profit_per_ac_day, is_valid) "
        "VALUES (1, 2, 1, 1000.0, 1)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))


def test_heatmap_panel_uses_textcontent_not_html_concat(heatmap_db_with_xss_name) -> None:
    client = TestClient(app)
    r = client.get("/api/heatmap-panel", params={"hub": "KHI"})
    assert r.status_code == 200
    body = r.text
    assert "title.textContent = m.iata" in body
    assert "small.textContent" in body
    assert "document.createElement('div')" in body
    assert "bindPopup(`" not in body
