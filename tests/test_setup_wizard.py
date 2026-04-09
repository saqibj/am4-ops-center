from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.state as app_state
from dashboard.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_setup_pages_render(client: TestClient) -> None:
    for path in ("/setup", "/setup/credentials", "/setup/hubs", "/setup/extract", "/setup/fleet"):
        r = client.get(path)
        assert r.status_code == 200, path


def test_setup_hubs_save_and_complete_requires_extract(client: TestClient) -> None:
    r = client.post("/setup/hubs", data={"hubs": "KHI,DXB"})
    assert r.status_code == 200
    assert "Saved 2 hub(s)." in r.text

    r2 = client.post("/setup/complete", follow_redirects=False)
    assert r2.status_code == 307
    assert r2.headers.get("location") == "/setup/extract"


def test_setup_extract_progress_partial(client: TestClient) -> None:
    app_state.set_state_value("setup_hubs", "KHI")
    r = client.get("/setup/extract/progress")
    assert r.status_code == 200
    assert "hubs" in r.text.lower()

