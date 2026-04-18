"""Unit tests for ``app.core.vip_pricing``."""

from __future__ import annotations

import pytest

from app.core.vip_pricing import (
    VIP_BASE_MULT,
    adjust_rows_for_route_type,
    compute_vip_profit,
    vip_ticket_prices,
)


def _expected_vip_y_easy(d_km: float) -> float:
    base_y = 0.4 * d_km + 170.0
    return base_y * VIP_BASE_MULT * 1.22


def test_vip_ticket_prices_5000km_easy_matches_formula() -> None:
    d = 5000.0
    y, j, f = vip_ticket_prices(d, realism=False)
    by, bj, bf = (0.4 * d + 170.0, 0.8 * d + 560.0, 1.2 * d + 1200.0)
    assert y == pytest.approx(by * VIP_BASE_MULT * 1.22)
    assert j == pytest.approx(bj * VIP_BASE_MULT * 1.195)
    assert f == pytest.approx(bf * VIP_BASE_MULT * 1.175)
    assert y == pytest.approx(_expected_vip_y_easy(d))


def test_realism_vs_easy_ticket_prices_differ() -> None:
    d = 3200.0
    ye, je, fe = vip_ticket_prices(d, realism=False)
    yr, jr, fr = vip_ticket_prices(d, realism=True)
    assert (ye, je, fe) != (yr, jr, fr)


def test_vip_profit_exceeds_pax_profit_mock_row() -> None:
    d = 4000.0
    cy, cj, cf = 42, 28, 8
    pax_profit = 55_000.0
    trips = 3
    out = compute_vip_profit(
        d, cy, cj, cf, pax_profit, None, trips, realism=False
    )
    by, bj, bf = (0.4 * d + 170.0, 0.8 * d + 560.0, 1.2 * d + 1200.0)
    pax_inc = (
        cy * by * 1.10 + cj * bj * 1.08 + cf * bf * 1.06
    )
    assert out["vip_profit_per_trip"] > pax_profit
    assert out["vip_profit_per_trip"] == pytest.approx(
        out["vip_income_per_trip"] - (pax_inc - pax_profit)
    )
    assert out["vip_profit_per_ac_day"] == pytest.approx(
        out["vip_profit_per_trip"] * trips
    )


def test_charter_rows_unchanged_values() -> None:
    row = {
        "distance_km": 1000.0,
        "config_y": 10,
        "config_j": 0,
        "config_f": 0,
        "profit_per_trip": 12345.0,
        "profit_per_ac_day": 37035.0,
        "trips_per_day": 3,
    }
    adj = adjust_rows_for_route_type([row], "charter", realism=False)
    assert len(adj) == 1
    assert adj[0]["profit_per_trip"] == row["profit_per_trip"]
    assert adj[0]["profit_per_ac_day"] == row["profit_per_ac_day"]


def test_zero_seats_no_error() -> None:
    out = compute_vip_profit(
        2000.0, 0, 0, 0, 0.0, None, 2, realism=False
    )
    assert out["vip_income_per_trip"] == 0.0
    assert out["vip_profit_per_trip"] == 0.0
    assert out["vip_profit_per_ac_day"] == 0.0


def test_adjust_vip_updates_profit_fields() -> None:
    row = {
        "distance_km": 4000.0,
        "config_y": 42,
        "config_j": 28,
        "config_f": 8,
        "profit_per_trip": 55_000.0,
        "profit_per_ac_day": 165_000.0,
        "trips_per_day": 3,
    }
    vip_rows = adjust_rows_for_route_type([row], "vip", realism=False)
    assert vip_rows[0]["profit_per_trip"] != row["profit_per_trip"]
    assert vip_rows[0]["profit_per_ac_day"] != row["profit_per_ac_day"]
    pax_rows = adjust_rows_for_route_type([row], "pax", realism=False)
    assert pax_rows[0]["profit_per_trip"] == row["profit_per_trip"]
