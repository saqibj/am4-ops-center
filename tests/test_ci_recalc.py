"""Tests for core.ci_recalc — post-extraction CI scaling engine."""

from __future__ import annotations

import math
import sqlite3

import pytest

from core.ci_recalc import (
    apply_ci_adjustments,
    build_fleet_ci_map,
    contribution_factor,
    fuel_co2_factor,
    recalc_row,
    speed_factor,
)


# ---------------------------------------------------------------------------
# Factor functions
# ---------------------------------------------------------------------------


class TestSpeedFactor:
    def test_ci200_is_unity(self):
        assert speed_factor(200) == pytest.approx(1.0)

    def test_ci0(self):
        assert speed_factor(0) == pytest.approx(0.3)

    def test_ci100(self):
        assert speed_factor(100) == pytest.approx(0.65)


class TestFuelCo2Factor:
    def test_ci200_is_unity(self):
        assert fuel_co2_factor(200) == pytest.approx(1.0)

    def test_ci0(self):
        assert fuel_co2_factor(0) == pytest.approx(0.9)

    def test_ci100(self):
        assert fuel_co2_factor(100) == pytest.approx(0.95)


class TestContributionFactor:
    def test_ci200_is_unity(self):
        assert contribution_factor(200) == pytest.approx(1.0)

    def test_ci0(self):
        assert contribution_factor(0) == pytest.approx(3.0)

    def test_ci100(self):
        assert contribution_factor(100) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Row recalculation
# ---------------------------------------------------------------------------


def _base_row(*, ci: int = 200, aircraft_id: int = 42) -> dict:
    """A realistic route_aircraft row at CI=200 (all factors = 1.0)."""
    return {
        "aircraft_id": aircraft_id,
        "flight_time_hrs": 10.0,
        "fuel_cost": 50000.0,
        "co2_cost": 10000.0,
        "repair_cost": 5000.0,
        "acheck_cost": 2000.0,
        "income": 200000.0,
        "contribution": 83.0,
        "trips_per_day": 1,
        "profit_per_trip": 133000.0,  # 200k - 50k - 10k - 5k - 2k
        "profit_per_ac_day": 133000.0,
        "income_per_ac_day": 200000.0,
        "ci": ci,
        "origin_id": 1,
        "dest_id": 2,
        "distance_km": 19850.0,
    }


class TestRecalcRow:
    def test_ci200_is_noop(self):
        row = _base_row()
        out = recalc_row(row, 200)
        assert out["flight_time_hrs"] == pytest.approx(10.0)
        assert out["fuel_cost"] == pytest.approx(50000.0)
        assert out["contribution"] == pytest.approx(83.0)
        assert out["ci"] == 200

    def test_ci100_contribution_doubles(self):
        row = _base_row()
        out = recalc_row(row, 100)
        # contribution_factor(100) = 2.0
        assert out["contribution"] == pytest.approx(83.0 * 2.0)

    def test_ci100_fuel_decreases(self):
        row = _base_row()
        out = recalc_row(row, 100)
        # fuel_co2_factor(100) = 0.95
        assert out["fuel_cost"] == pytest.approx(50000.0 * 0.95)
        assert out["co2_cost"] == pytest.approx(10000.0 * 0.95)

    def test_ci100_flight_time_increases(self):
        row = _base_row()
        out = recalc_row(row, 100)
        # speed_factor(100) = 0.65 → ft = 10 / 0.65 ≈ 15.385
        assert out["flight_time_hrs"] == pytest.approx(10.0 / 0.65, rel=1e-3)

    def test_ci100_profit_per_trip_recalculated(self):
        row = _base_row()
        out = recalc_row(row, 100)
        expected_fuel = 50000.0 * 0.95
        expected_co2 = 10000.0 * 0.95
        expected_profit = 200000.0 - expected_fuel - expected_co2 - 5000.0 - 2000.0
        assert out["profit_per_trip"] == pytest.approx(expected_profit)

    def test_ci_field_updated(self):
        row = _base_row()
        out = recalc_row(row, 150)
        assert out["ci"] == 150

    def test_does_not_mutate_original(self):
        row = _base_row()
        _ = recalc_row(row, 100)
        assert row["ci"] == 200
        assert row["fuel_cost"] == 50000.0

    def test_short_flight_time_increases_tpd(self):
        """A short 2hr flight at CI=200 → tpd=6. At CI=200 stays 6."""
        row = _base_row()
        row["flight_time_hrs"] = 2.0
        row["trips_per_day"] = 6
        out = recalc_row(row, 200)
        assert out["trips_per_day"] == 6

    def test_ci0_triples_contribution(self):
        row = _base_row()
        out = recalc_row(row, 0)
        assert out["contribution"] == pytest.approx(83.0 * 3.0)

    def test_tpd_minimum_is_1(self):
        """Even with very slow speed, tpd should be at least 1."""
        row = _base_row()
        row["flight_time_hrs"] = 11.0  # round trip 22h at CI=200
        out = recalc_row(row, 50)
        # speed_factor(50) = 0.475 → ft = 11/0.475 ≈ 23.16h → round trip 46.3h > 24 → tpd=1
        assert out["trips_per_day"] >= 1

    def test_passthrough_columns_unchanged(self):
        row = _base_row()
        row["origin_id"] = 999
        row["stopover_iata"] = "SIN"
        out = recalc_row(row, 100)
        assert out["origin_id"] == 999
        assert out["stopover_iata"] == "SIN"


# ---------------------------------------------------------------------------
# Fleet CI map
# ---------------------------------------------------------------------------


def _mem_db_with_fleet(fleet_rows: list[tuple[int, int]]) -> sqlite3.Connection:
    """In-memory DB with a minimal my_fleet table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE my_fleet (aircraft_id INTEGER PRIMARY KEY, ci INTEGER NOT NULL DEFAULT 200)"
    )
    for ac_id, ci in fleet_rows:
        conn.execute("INSERT INTO my_fleet (aircraft_id, ci) VALUES (?, ?)", (ac_id, ci))
    conn.commit()
    return conn


class TestBuildFleetCiMap:
    def test_empty_fleet(self):
        conn = _mem_db_with_fleet([])
        assert build_fleet_ci_map(conn) == {}

    def test_all_default_200(self):
        conn = _mem_db_with_fleet([(1, 200), (2, 200)])
        assert build_fleet_ci_map(conn) == {}

    def test_mixed(self):
        conn = _mem_db_with_fleet([(1, 100), (2, 200), (3, 50)])
        m = build_fleet_ci_map(conn)
        assert m == {1: 100, 3: 50}
        assert 2 not in m

    def test_no_table_returns_empty(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        assert build_fleet_ci_map(conn) == {}


# ---------------------------------------------------------------------------
# Batch adjustment
# ---------------------------------------------------------------------------


class TestApplyCiAdjustments:
    def test_empty_map_returns_unchanged(self):
        conn = _mem_db_with_fleet([])
        rows = [_base_row(aircraft_id=1)]
        out = apply_ci_adjustments(conn, rows)
        assert out[0]["ci"] == 200
        assert out[0]["fuel_cost"] == 50000.0

    def test_adjusts_matching_aircraft(self):
        conn = _mem_db_with_fleet([(42, 100)])
        rows = [_base_row(aircraft_id=42)]
        out = apply_ci_adjustments(conn, rows)
        assert out[0]["ci"] == 100
        assert out[0]["contribution"] == pytest.approx(83.0 * 2.0)

    def test_leaves_non_matching_aircraft(self):
        conn = _mem_db_with_fleet([(42, 100)])
        rows = [_base_row(aircraft_id=99)]
        out = apply_ci_adjustments(conn, rows)
        assert out[0]["ci"] == 200
        assert out[0]["fuel_cost"] == 50000.0

    def test_mixed_fleet(self):
        conn = _mem_db_with_fleet([(10, 100), (20, 50)])
        rows = [
            _base_row(aircraft_id=10),
            _base_row(aircraft_id=20),
            _base_row(aircraft_id=30),  # not in fleet → unchanged
        ]
        out = apply_ci_adjustments(conn, rows)
        assert out[0]["ci"] == 100
        assert out[1]["ci"] == 50
        assert out[2]["ci"] == 200

    def test_prebuilt_map(self):
        conn = _mem_db_with_fleet([])  # empty, but map overrides
        rows = [_base_row(aircraft_id=42)]
        out = apply_ci_adjustments(conn, rows, fleet_ci_map={42: 150})
        assert out[0]["ci"] == 150
