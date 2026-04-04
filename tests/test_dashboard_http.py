"""Smoke tests: app imports, static assets, and key HTML pages (no DB required for many paths)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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
    r = client.get("/")
    assert r.status_code == 200
    assert "AM4 Ops Center" in r.text or "Overview" in r.text


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
