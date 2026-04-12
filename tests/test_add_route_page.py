"""Smoke tests for Add route page."""

from __future__ import annotations

import dashboard.db as dbm
from database.schema import create_schema, get_connection
from fastapi.testclient import TestClient

from dashboard.server import app


def test_routes_add_page_renders(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "add_route.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI'), (2, 'DXB')")
    conn.execute(
        "INSERT INTO my_hubs (airport_id, is_active, last_extract_status) VALUES (1, 1, 'ok')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    client = TestClient(app)
    r = client.get("/routes/add")
    assert r.status_code == 200
    assert "Add route" in r.text
    assert "aircraft-select-target" in r.text
    assert "add-route-hub" in r.text
