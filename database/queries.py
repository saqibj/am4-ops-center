"""Predefined SQL queries and small helpers."""

from __future__ import annotations

import sqlite3
from typing import Any

BEST_ROUTES_FOR_HUB = """
SELECT * FROM v_best_routes
WHERE hub = ?
ORDER BY profit_per_ac_day DESC
LIMIT ?;
"""

BEST_AIRCRAFT_FOR_ROUTE = """
SELECT ac.shortname, ac.name, ra.profit_per_ac_day, ra.trips_per_day,
       ra.config_y, ra.config_j, ra.config_f, ra.flight_time_hrs
FROM route_aircraft ra
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.origin_id = ? AND ra.dest_id = ? AND ra.is_valid = 1
ORDER BY ra.profit_per_ac_day DESC;
"""

TOP_HUBS_BY_AVG_PROFIT = """
SELECT a.iata, a.name, a.country,
       COUNT(*) AS total_routes,
       AVG(ra.profit_per_ac_day) AS avg_profit,
       MAX(ra.profit_per_ac_day) AS max_profit
FROM route_aircraft ra
JOIN airports a ON ra.origin_id = a.id
WHERE ra.is_valid = 1
GROUP BY ra.origin_id
ORDER BY avg_profit DESC
LIMIT ?;
"""

TOP_BY_CONTRIBUTION = """
SELECT * FROM v_best_routes
ORDER BY contribution DESC
LIMIT ?;
"""

AIRCRAFT_COMPARISON_FOR_HUB = """
SELECT ac.shortname, ac.type, ac.cost,
       COUNT(*) AS viable_routes,
       AVG(ra.profit_per_ac_day) AS avg_daily_profit,
       SUM(ra.profit_per_ac_day) AS total_daily_profit_potential
FROM route_aircraft ra
JOIN aircraft ac ON ra.aircraft_id = ac.id
WHERE ra.origin_id = ? AND ra.is_valid = 1
GROUP BY ra.aircraft_id
ORDER BY avg_daily_profit DESC;
"""

ROUTES_WITH_STOPOVERS = """
SELECT * FROM v_best_routes
WHERE needs_stopover = 1
ORDER BY profit_per_ac_day DESC;
"""

ROUTES_BY_HAUL = """
SELECT
    CASE
        WHEN distance_km < 3000 THEN 'short_haul'
        WHEN distance_km < 7000 THEN 'medium_haul'
        ELSE 'long_haul'
    END AS haul_type,
    aircraft, hub, destination,
    profit_per_ac_day, contribution
FROM v_best_routes
ORDER BY haul_type, profit_per_ac_day DESC;
"""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    cur = conn.execute(sql, params)
    return cur.fetchall()


def hub_id(conn: sqlite3.Connection, iata: str) -> int | None:
    row = conn.execute("SELECT id FROM airports WHERE UPPER(iata) = UPPER(?) LIMIT 1", (iata,)).fetchone()
    return int(row[0]) if row else None
