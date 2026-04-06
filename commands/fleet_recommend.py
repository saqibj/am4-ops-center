"""Shared hub + budget aircraft recommendation rows (CLI + dashboard).

Recommendations use route data from SQLite; AM4 pricing/discount assumptions follow the
same UserConfig as extraction. ``total_planes_owned`` is driven by my_fleet when set
from dashboard refresh or CLI extract (see extract metadata / ``--planes-owned``).
"""

from __future__ import annotations

import sqlite3

_HIDE_OWNED_SQL = """
      AND NOT EXISTS (
        SELECT 1 FROM my_fleet mf_hide
        WHERE mf_hide.aircraft_id = ac.id AND COALESCE(mf_hide.quantity, 0) > 0
      )
"""


def _recommend_sql(hide_owned: bool) -> str:
    hide = _HIDE_OWNED_SQL if hide_owned else ""
    return f"""
    SELECT ac.shortname, ac.name, ac.type, ac.cost,
           COUNT(*) AS routes,
           AVG(ra.profit_per_ac_day) AS avg_daily_profit,
           MAX(ra.profit_per_ac_day) AS best_daily_profit,
           COALESCE(MAX(mf.quantity), 0) AS owned_qty
    FROM route_aircraft ra
    JOIN aircraft ac ON ra.aircraft_id = ac.id
    LEFT JOIN my_fleet mf ON mf.aircraft_id = ac.id
    WHERE ra.is_valid = 1 AND ra.origin_id = ? AND ac.cost <= ?
    {hide}
    GROUP BY ra.aircraft_id
    ORDER BY avg_daily_profit DESC
    LIMIT ?
"""


def fleet_recommend_rows(
    conn: sqlite3.Connection,
    hub_iata: str,
    budget: int,
    top_n: int,
    *,
    hide_owned: bool = False,
) -> tuple[list[dict], str | None]:
    """
    Aircraft at ``hub_iata`` with ``ac.cost <= budget``, ranked by avg daily profit.

    Returns ``(rows, err)``. ``err`` is ``None`` on success, or ``"unknown_hub"`` if
    the IATA is missing. Each row includes ``owned_qty`` from ``my_fleet`` (0 if none),
    ``days_to_breakeven_avg`` and ``days_to_breakeven_best`` (``None`` if not computable),
    and ``days_to_breakeven`` as an alias for the **best-route** case (same as
    ``days_to_breakeven_best``), since an aircraft flies one route at a time.

    If ``hide_owned`` is true, aircraft with ``my_fleet.quantity > 0`` are excluded
    before the ``LIMIT`` (top-N applies to the filtered set).
    """
    hub = (hub_iata or "").strip()
    if not hub:
        return [], "unknown_hub"

    hub_row = conn.execute(
        "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
        [hub],
    ).fetchone()
    if not hub_row:
        return [], "unknown_hub"

    origin_id = int(hub_row[0])
    cur = conn.execute(
        _recommend_sql(hide_owned),
        (origin_id, int(budget), int(top_n)),
    )
    col_names = [d[0] for d in cur.description]
    rows: list[dict] = []
    for tup in cur.fetchall():
        r = dict(zip(col_names, tup, strict=True))
        r["owned_qty"] = int(r.get("owned_qty") or 0)
        avg = float(r.get("avg_daily_profit") or 0)
        best = float(r.get("best_daily_profit") or 0)
        cost = int(r.get("cost") or 0)
        r["days_to_breakeven_avg"] = (
            round(cost / avg, 1) if avg > 0 and cost > 0 else None
        )
        r["days_to_breakeven_best"] = (
            round(cost / best, 1) if best > 0 and cost > 0 else None
        )
        r["days_to_breakeven"] = r["days_to_breakeven_best"]
        rows.append(r)
    return rows, None
