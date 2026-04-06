"""SEC-10: only one hub extraction at a time per process."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dbm
from dashboard.server import app
from dashboard.routes import api_routes
from database.schema import create_schema, get_connection


@pytest.fixture
def hub_refresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "hub_lock.db"
    conn = get_connection(db_path)
    create_schema(conn)
    conn.execute("INSERT INTO airports (id, iata) VALUES (1, 'KHI')")
    conn.execute("INSERT INTO my_hubs (airport_id, is_active) VALUES (1, 1)")
    conn.commit()
    row = conn.execute("SELECT id FROM my_hubs LIMIT 1").fetchone()
    assert row is not None
    hub_id = int(row[0])
    conn.close()
    s = str(db_path)
    monkeypatch.setattr(dbm, "DB_PATH", s)
    monkeypatch.setattr(api_routes, "DB_PATH", s)
    monkeypatch.setattr(api_routes, "_am4_init", lambda: None)
    return hub_id


def test_extraction_lock_second_acquire_fails() -> None:
    assert api_routes._try_acquire_extraction_lock() is True
    try:
        assert api_routes._try_acquire_extraction_lock() is False
    finally:
        api_routes._release_extraction_lock()


def test_concurrent_hub_refresh_second_gets_busy_message(hub_refresh_db) -> None:
    hub_id = hub_refresh_db
    entered = threading.Event()

    def slow_refresh(*_a, **_k) -> None:
        entered.set()
        time.sleep(2)

    with patch("extractors.routes.refresh_single_hub", side_effect=slow_refresh):
        client = TestClient(app)
        errors: list[BaseException] = []

        def run_refresh() -> None:
            try:
                client.post("/api/hubs/refresh", data={"hub_id": str(hub_id)})
            except BaseException as exc:
                errors.append(exc)

        th = threading.Thread(target=run_refresh)
        th.start()
        assert entered.wait(timeout=5)
        r2 = client.post("/api/hubs/refresh", data={"hub_id": str(hub_id)})
        assert r2.status_code == 200
        assert "Another extraction is already in progress" in r2.text
        th.join(timeout=15)

    assert not errors


def test_refresh_stale_busy_while_single_hub_refresh_runs(hub_refresh_db) -> None:
    hub_id = hub_refresh_db
    entered = threading.Event()

    def slow_refresh(*_a, **_k) -> None:
        entered.set()
        time.sleep(2)

    with patch("extractors.routes.refresh_single_hub", side_effect=slow_refresh):
        client = TestClient(app)
        th = threading.Thread(
            target=lambda: client.post("/api/hubs/refresh", data={"hub_id": str(hub_id)})
        )
        th.start()
        assert entered.wait(timeout=5)
        r2 = client.post("/api/hubs/refresh-stale")
        assert r2.status_code == 200
        assert "Another extraction is already in progress" in r2.text
        th.join(timeout=15)
