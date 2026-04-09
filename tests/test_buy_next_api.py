"""Edge-case and validation tests for Buy Next HTMX APIs (`/api/buy-next`, `/api/buy-next-global`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dashboard_db
from dashboard.server import app
from dashboard.routes.api.recommendations import _parse_buy_next_budget


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def absent_am4_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    p = tmp_path / "no_am4_data.db"
    assert not p.exists()
    monkeypatch.setattr(dashboard_db, "DB_PATH", str(p))


@pytest.mark.parametrize(
    ("raw", "expected_val", "expected_err"),
    [
        (None, None, "missing"),
        ("", None, "missing"),
        ("  ", None, "missing"),
        ("0", 0, None),
        ("100000000.50", 100000000, None),
        ("-1", None, "invalid"),
        ("abc", None, "invalid"),
    ],
)
def test_parse_buy_next_budget(
    raw: str | None, expected_val: int | None, expected_err: str | None
) -> None:
    val, err = _parse_buy_next_budget(raw)
    assert val == expected_val
    assert err == expected_err


def test_buy_next_no_hub_returns_prompt(client: TestClient, absent_am4_db: None) -> None:
    r = client.get("/api/buy-next", params={"budget": "100000000"})
    assert r.status_code == 200
    assert "Pick a hub" in r.text


def test_buy_next_missing_budget_returns_prompt(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/api/buy-next", params={"hub": "DXB"})
    assert r.status_code == 200
    assert "Pick a hub" in r.text


def test_buy_next_invalid_budget_returns_amber(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get(
        "/api/buy-next", params={"hub": "DXB", "budget": "not-a-number"}
    )
    assert r.status_code == 200
    assert "valid budget" in r.text


def test_buy_next_negative_budget_returns_amber(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/api/buy-next", params={"hub": "DXB", "budget": "-100"})
    assert r.status_code == 200
    assert "valid budget" in r.text


def test_buy_next_database_missing_returns_amber(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get(
        "/api/buy-next", params={"hub": "DXB", "budget": "200000000"}
    )
    assert r.status_code == 200
    assert "Database not found" in r.text


def test_buy_next_global_missing_budget_returns_prompt(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/api/buy-next-global")
    assert r.status_code == 200
    assert "budget" in r.text.lower()


def test_buy_next_global_invalid_budget_returns_amber(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/api/buy-next-global", params={"budget": "xyz"})
    assert r.status_code == 200
    assert "valid budget" in r.text


def test_buy_next_global_database_missing_returns_amber(
    client: TestClient, absent_am4_db: None
) -> None:
    r = client.get("/api/buy-next-global", params={"budget": "200000000"})
    assert r.status_code == 200
    assert "Database not found" in r.text


def test_buy_next_limit_over_max_returns_422(client: TestClient) -> None:
    r = client.get(
        "/api/buy-next",
        params={"hub": "DXB", "budget": "1", "limit": 99999},
    )
    assert r.status_code == 422


def test_buy_next_global_limit_over_max_returns_422(client: TestClient) -> None:
    r = client.get(
        "/api/buy-next-global",
        params={"budget": "1", "limit": 99999},
    )
    assert r.status_code == 422
