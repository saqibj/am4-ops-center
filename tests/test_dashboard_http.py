"""Smoke tests: app imports, static assets, and key HTML pages (no DB required for many paths)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dashboard_db
from dashboard.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def absent_am4_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Point dashboard at a non-existent DB so routes that use get_db() stay fast and deterministic."""
    p = tmp_path / "no_am4ops.db"
    assert not p.exists()
    monkeypatch.setattr(dashboard_db, "DB_PATH", str(p))


def test_static_theme_css(client: TestClient) -> None:
    r = client.get("/static/css/theme.css")
    assert r.status_code == 200
    assert b"am4-table" in r.content


def test_static_settings_store_js(client: TestClient) -> None:
    r = client.get("/static/js/settings-store.js")
    assert r.status_code == 200
    assert b"Am4UiSettings" in r.content


def test_settings_page_renders(client: TestClient) -> None:
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Settings" in r.text
    assert "settings-page.js" in r.text


def test_index_renders(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location") == "/setup"


def test_setup_page_renders(client: TestClient) -> None:
    r = client.get("/setup")
    assert r.status_code == 200
    assert "Setup" in r.text


def test_health_reports_setup_state(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "setup_complete" in body


def test_extraction_deltas_page_renders(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/extraction-deltas")
    assert r.status_code == 200
    assert "Extraction deltas" in r.text
    assert 'hx-get="/api/extraction-deltas"' in r.text


def test_extraction_deltas_api_without_db(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/api/extraction-deltas")
    assert r.status_code == 200
    assert "Database not found" in r.text


def test_buy_next_page_includes_saved_filters_bar(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/buy-next")
    assert r.status_code == 200
    assert "sf-wrap-buy-next" in r.text
    assert "saved-filters.js" in r.text or "Saved filters" in r.text


def test_buy_next_global_page_includes_saved_filters_bar(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/buy-next/global")
    assert r.status_code == 200
    assert "sf-wrap-buy-next-global" in r.text
    assert "buynext-global-filters" in r.text


# HTMX bubbles afterRequest to ancestors; without this guard, child requests (e.g. search)
# can incorrectly trigger form.reset() on the parent form.
_HTMX_AFTER_REQUEST_ELT_GUARD = "event.detail.elt !== event.currentTarget"


def test_my_inventory_pages_form_after_request_elt_guard(client: TestClient) -> None:
    """Regression: add-route / add-hub / add-fleet forms must not reset on bubbled HTMX events."""
    for path, form_marker in (
        ("/my-routes", 'id="routes-add-form"'),
        ("/my-hubs", 'id="hub-add-form"'),
        ("/my-fleet", 'id="fleet-add-form"'),
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.text
        assert form_marker in body, path
        assert _HTMX_AFTER_REQUEST_ELT_GUARD in body, path
        assert body.index(form_marker) < body.index(_HTMX_AFTER_REQUEST_ELT_GUARD), path
