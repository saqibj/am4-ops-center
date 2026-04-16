"""Pure helpers to diff two route_aircraft_snapshot-style maps (testable, no FastAPI)."""

from __future__ import annotations

import heapq
from typing import Any

SnapshotKey = tuple[int, int, int]
SnapshotMap = dict[SnapshotKey, dict]


def pct_change(pa: float | None, pb: float | None) -> float:
    a = float(pa or 0)
    b = float(pb or 0)
    if abs(a) < 1e-9:
        return float("inf") if abs(b) > 1e-9 else 0.0
    return (b - a) / abs(a) * 100.0


def rows_for_smallest_keys(
    keys: set[SnapshotKey], row_map: SnapshotMap, ntake: int
) -> list[dict]:
    """Row dicts for the lexicographically smallest ``ntake`` keys (same as sorted(keys)[:ntake])."""
    if not keys or ntake <= 0:
        return []
    picked = heapq.nsmallest(min(ntake, len(keys)), keys)
    return [row_map[k] for k in picked]


def compute_extraction_delta_view(
    ma: SnapshotMap,
    mb: SnapshotMap,
    min_pct: float,
    limit: int,
) -> dict[str, Any]:
    """Diff two snapshot maps keyed by (origin_id, dest_id, aircraft_id). Template-ready payload.

    Snapshots are dict-keyed in the caller (O(n)). For appeared/disappeared sections only the first
    ``limit`` rows are needed; we select those keys with ``heapq.nsmallest`` in O(k log limit) instead
    of sorting all differing keys O(k log k) when k is large.
    """
    keys_a = set(ma.keys())
    keys_b = set(mb.keys())
    only_b = keys_b - keys_a
    only_a = keys_a - keys_b
    n_appeared = len(only_b)
    n_disappeared = len(only_a)
    appeared = rows_for_smallest_keys(only_b, mb, limit)
    disappeared = rows_for_smallest_keys(only_a, ma, limit)

    movers: list[dict] = []
    flip_to_profit = 0
    flip_to_loss = 0
    hub_deltas: dict[str, list[float]] = {}

    for k in keys_a & keys_b:
        ra, rb = ma[k], mb[k]
        pa = float(ra.get("profit_per_ac_day") or 0)
        pb = float(rb.get("profit_per_ac_day") or 0)
        va = int(ra.get("is_valid") or 0)
        vb = int(rb.get("is_valid") or 0)
        if va == 0 and vb == 1 and pb > 0:
            flip_to_profit += 1
        if va == 1 and vb == 0:
            flip_to_loss += 1
        pct = pct_change(pa, pb)
        if pct == float("inf") or abs(pct) >= min_pct:
            movers.append(
                {
                    "hub": ra["hub_iata"],
                    "dest": ra["dest_iata"],
                    "ac": ra["ac_short"],
                    "profit_a": pa,
                    "profit_b": pb,
                    "pct": pct,
                    "pct_display": "∞" if pct == float("inf") else f"{pct:+.1f}%",
                    "valid_a": va,
                    "valid_b": vb,
                }
            )
        h = str(ra.get("hub_iata") or "")
        hub_deltas.setdefault(h, []).append(pb - pa)

    movers.sort(key=lambda x: abs(x["profit_b"] - x["profit_a"]), reverse=True)

    hub_avg = [
        {
            "hub": h,
            "avg_delta": sum(v) / len(v) if v else 0.0,
            "n": len(v),
        }
        for h, v in sorted(hub_deltas.items(), key=lambda x: -abs(sum(x[1]) / len(x[1]) if x[1] else 0))
    ][:20]

    return {
        "appeared": appeared,
        "disappeared": disappeared,
        "movers": movers[:limit],
        "n_appeared": n_appeared,
        "n_disappeared": n_disappeared,
        "n_movers": len(movers),
        "flip_to_profit": flip_to_profit,
        "flip_to_loss": flip_to_loss,
        "hub_avg": hub_avg,
    }
