"""Pytest hooks and shared fixtures."""

from __future__ import annotations

import os

import pytest

# Must match env before any test imports dashboard.server (which loads auth).
DASHBOARD_TEST_TOKEN = "test-am4-routemine-dashboard-token"


def pytest_configure(config) -> None:
    os.environ["AM4_ROUTEMINE_TOKEN"] = DASHBOARD_TEST_TOKEN


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {DASHBOARD_TEST_TOKEN}"}
