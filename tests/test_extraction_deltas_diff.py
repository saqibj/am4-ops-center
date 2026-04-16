"""Golden + property tests for extraction snapshot diff (``compute_extraction_delta_view``)."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import pytest

from dashboard.extraction_delta_diff import (
    SnapshotMap,
    compute_extraction_delta_view,
    rows_for_smallest_keys,
)

_GOLDEN = Path(__file__).resolve().parent / "golden_extraction_deltas.json"

_SAMPLE_MA: SnapshotMap = {
    (100, 200, 1): {
        "origin_id": 100,
        "dest_id": 200,
        "aircraft_id": 1,
        "hub_iata": "LHR",
        "dest_iata": "BOS",
        "ac_short": "738",
        "profit_per_ac_day": 1000.0,
        "is_valid": 1,
        "income": 1,
    },
    (100, 201, 1): {
        "origin_id": 100,
        "dest_id": 201,
        "aircraft_id": 1,
        "hub_iata": "LHR",
        "dest_iata": "MIA",
        "ac_short": "738",
        "profit_per_ac_day": 500.0,
        "is_valid": 1,
        "income": 1,
    },
}
_SAMPLE_MB: SnapshotMap = {
    (100, 200, 1): {
        "origin_id": 100,
        "dest_id": 200,
        "aircraft_id": 1,
        "hub_iata": "LHR",
        "dest_iata": "BOS",
        "ac_short": "738",
        "profit_per_ac_day": 1200.0,
        "is_valid": 1,
        "income": 1,
    },
    (100, 202, 1): {
        "origin_id": 100,
        "dest_id": 202,
        "aircraft_id": 1,
        "hub_iata": "LHR",
        "dest_iata": "SFO",
        "ac_short": "738",
        "profit_per_ac_day": 800.0,
        "is_valid": 1,
        "income": 1,
    },
}


def _norm_for_json(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _norm_for_json(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_norm_for_json(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:
            return "nan"
        if obj == float("inf"):
            return "Infinity"
        if obj == float("-inf"):
            return "-Infinity"
    return obj


def test_compute_extraction_delta_view_matches_golden() -> None:
    ctx = compute_extraction_delta_view(_SAMPLE_MA, _SAMPLE_MB, 5.0, 75)
    expected_raw = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert _norm_for_json(ctx) == expected_raw


@pytest.mark.parametrize("limit", [1, 3, 10, 75, 500])
def test_rows_for_smallest_keys_matches_sorted_slice(limit: int) -> None:
    random.seed(42)
    keys = {(random.randint(1, 50), random.randint(1, 50), random.randint(1, 5)) for _ in range(200)}
    rm = {k: {"k": k} for k in keys}
    want = [rm[k] for k in sorted(keys)[: min(limit, len(keys))]]
    got = rows_for_smallest_keys(keys, rm, limit)
    assert got == want


def test_large_diff_top_k_is_fast() -> None:
    """Sanity: selecting limit rows from a large key-only diff stays sub-second (warm)."""
    random.seed(0)
    keys_b_only = {
        (i, j, 1)
        for i in range(300)
        for j in range(300)
    }  # 90k tuples
    rm = {k: {"origin_id": k[0], "dest_id": k[1], "aircraft_id": 1} for k in keys_b_only}
    t0 = time.perf_counter()
    rows_for_smallest_keys(keys_b_only, rm, 75)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 500.0, f"took {elapsed_ms:.0f}ms"
