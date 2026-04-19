"""Post-extraction CI recalculation.

The am4 C++ package hardcodes CI=200 internally (no parameter on RoutesSearch
or AircraftRoute.create). At CI=200 every scaling factor evaluates to 1.0,
so the am4 output IS the unscaled base. This module multiplies by the ratio
for the user's per-aircraft CI stored in ``my_fleet``.

Formulae (from abc8747.github.io/am4/formulae/):
  speed:        v = u × (0.0035 × CI + 0.3)
  fuel / CO₂:   cost ∝ (CI / 2000 + 0.9)
  contribution: C ∝ (3 − CI / 100)
"""

from __future__ import annotations

import logging
import math
import sqlite3

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Factor functions  (all return 1.0 at CI=200)
# ---------------------------------------------------------------------------


def speed_factor(ci: int) -> float:
    """Relative speed vs CI=200.  v = u × (0.0035 × CI + 0.3)."""
    return 0.0035 * ci + 0.3


def fuel_co2_factor(ci: int) -> float:
    """Relative fuel / CO₂ cost vs CI=200.  cost ∝ (CI/2000 + 0.9)."""
    return ci / 2000.0 + 0.9


def contribution_factor(ci: int) -> float:
    """Relative contribution vs CI=200.  C ∝ (3 − CI/100)."""
    return 3.0 - ci / 100.0


# ---------------------------------------------------------------------------
# Row-level recalculation
# ---------------------------------------------------------------------------


def recalc_row(row: dict, ci: int) -> dict:
    """Return a copy of *row* with columns rescaled from CI=200 to *ci*.

    Affected columns: ``flight_time_hrs``, ``fuel_cost``, ``co2_cost``,
    ``contribution``, ``trips_per_day``, ``profit_per_trip``,
    ``profit_per_ac_day``, ``income_per_ac_day``, ``ci``.

    ``income``, ``repair_cost``, ``acheck_cost`` are CI-independent and
    pass through unchanged.

    .. note::

       ``trips_per_day`` is recomputed as ``floor(24 / (2 × ft_new))``
       (minimum 1).  The am4 package may include turnaround time or
       rounding modes we cannot observe; treat this as an approximation.
    """
    out = dict(row)
    if ci == 200:
        return out  # no-op: all factors are 1.0

    sf = speed_factor(ci)
    fc = fuel_co2_factor(ci)
    cf = contribution_factor(ci)

    # --- flight time (inversely proportional to speed) ---
    ft_old = float(out.get("flight_time_hrs") or 0.0)
    ft_new = ft_old / sf if sf > 0 else ft_old
    out["flight_time_hrs"] = ft_new

    # --- trips per day (recompute from new flight time) ---
    if ft_new > 0:
        round_trip = 2.0 * ft_new
        tpd_new = max(1, math.floor(24.0 / round_trip)) if round_trip < 24.0 else 1
    else:
        tpd_new = int(out.get("trips_per_day") or 1)
    out["trips_per_day"] = tpd_new

    # --- fuel & CO₂ ---
    fuel_old = float(out.get("fuel_cost") or 0.0)
    co2_old = float(out.get("co2_cost") or 0.0)
    out["fuel_cost"] = fuel_old * fc
    out["co2_cost"] = co2_old * fc

    # --- contribution ---
    contrib_old = float(out.get("contribution") or 0.0)
    out["contribution"] = contrib_old * cf

    # --- derived profit ---
    income = float(out.get("income") or 0.0)
    repair = float(out.get("repair_cost") or 0.0)
    acheck = float(out.get("acheck_cost") or 0.0)
    profit_trip = income - out["fuel_cost"] - out["co2_cost"] - repair - acheck
    out["profit_per_trip"] = profit_trip
    out["profit_per_ac_day"] = profit_trip * tpd_new
    out["income_per_ac_day"] = income * tpd_new

    out["ci"] = ci
    return out


# ---------------------------------------------------------------------------
# Fleet CI map
# ---------------------------------------------------------------------------


def build_fleet_ci_map(conn: sqlite3.Connection) -> dict[int, int]:
    """{aircraft_id: ci} for fleet entries where CI != 200."""
    try:
        rows = conn.execute(
            "SELECT aircraft_id, ci FROM my_fleet WHERE ci != 200"
        ).fetchall()
    except sqlite3.OperationalError:
        # my_fleet table may not exist on a fresh DB.
        return {}
    return {int(r["aircraft_id"]): int(r["ci"]) for r in rows}


# ---------------------------------------------------------------------------
# Batch adjustment
# ---------------------------------------------------------------------------


def apply_ci_adjustments(
    conn: sqlite3.Connection,
    route_rows: list[dict],
    fleet_ci_map: dict[int, int] | None = None,
) -> list[dict]:
    """Adjust *route_rows* for per-aircraft CI from ``my_fleet``.

    Rows whose ``aircraft_id`` is not in the map (or has CI=200) are
    returned unchanged.  Pass a pre-built *fleet_ci_map* to avoid
    re-querying when processing multiple hubs.
    """
    if fleet_ci_map is None:
        fleet_ci_map = build_fleet_ci_map(conn)
    if not fleet_ci_map:
        return route_rows  # nothing to adjust

    adjusted = 0
    result: list[dict] = []
    for row in route_rows:
        ac_id = int(row.get("aircraft_id", -1))
        ci = fleet_ci_map.get(ac_id)
        if ci is not None:
            result.append(recalc_row(row, ci))
            adjusted += 1
        else:
            result.append(row)
    if adjusted:
        log.info("CI recalc: adjusted %d / %d route rows", adjusted, len(route_rows))
    return result
