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
