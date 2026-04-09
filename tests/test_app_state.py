from __future__ import annotations

from fastapi.testclient import TestClient

import app.state as app_state
import dashboard.db as dashboard_db
from database.schema import create_schema, get_connection
from dashboard.server import app


def test_setup_state_helpers_and_root_guard(monkeypatch, tmp_path) -> None:
    db = tmp_path / "state.db"
    monkeypatch.setattr(dashboard_db, "DB_PATH", str(db))

    app_state.reset_setup()
    assert app_state.is_setup_complete() is False

    client = TestClient(app)
    r1 = client.get("/", follow_redirects=False)
    assert r1.status_code == 307
    assert r1.headers.get("location") == "/setup"

    app_state.mark_setup_complete()
    assert app_state.is_setup_complete() is True

    conn = get_connection(str(db))
    try:
        create_schema(conn)
    finally:
        conn.close()

    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 200
