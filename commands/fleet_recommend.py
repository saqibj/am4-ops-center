"""Shared hub + budget aircraft recommendation rows (CLI + dashboard)."""

from __future__ import annotations

import sqlite3

_RECOMMEND_SQL = """
    SELECT ac.shortname, ac.name, ac.type, ac.cost,
           COUNT(*) AS routes,
           AVG(ra.profit_per_ac_day) AS avg_daily_profit,
           MAX(ra.profit_per_ac_day) AS best_daily_profit
    FROM route_aircraft ra
    JOIN aircraft ac ON ra.aircraft_id = ac.id
    WHERE ra.is_valid = 1 AND ra.origin_id = ? AND ac.cost <= ?
    GROUP BY ra.aircraft_id
    ORDER BY avg_daily_profit DESC
    LIMIT ?
"""


def fleet_recommend_rows(
    conn: sqlite3.Connection,
    hub_iata: str,
    budget: int,
    top_n: int,
) -> tuple[list[dict], str | None]:
    """
    Aircraft at ``hub_iata`` with ``ac.cost <= budget``, ranked by avg daily profit.

    Returns ``(rows, err)``. ``err`` is ``None`` on success, or ``"unknown_hub"`` if
    the IATA is missing. Each row includes ``days_to_breakeven`` (``None`` if not
    computable): ``cost / avg_daily_profit`` when both are positive.
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
        _RECOMMEND_SQL,
        (origin_id, int(budget), int(top_n)),
    )
    col_names = [d[0] for d in cur.description]
    rows: list[dict] = []
    for tup in cur.fetchall():
        r = dict(zip(col_names, tup, strict=True))
        avg = float(r.get("avg_daily_profit") or 0)
        cost = int(r.get("cost") or 0)
        r["days_to_breakeven"] = (
            round(cost / avg, 1) if avg > 0 and cost > 0 else None
        )
        rows.append(r)
    return rows, None
