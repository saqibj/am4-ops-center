"""Hub domain helpers: explorer-visible hubs (my_hubs) and full hub deletion."""

from __future__ import annotations

import sqlite3

# Hubs shown in Hub Explorer, Buy Next, etc.: managed + successfully extracted at least once.
_EXPLORER_HUB_WHERE = (
    "h.is_active = 1 AND h.last_extract_status = 'ok' "
    "AND h.iata IS NOT NULL AND TRIM(h.iata) != ''"
)

SQL_EXPLORER_HUBS_WITH_NAMES = f"""
    SELECT h.iata AS iata, COALESCE(h.name, '') AS name
    FROM v_my_hubs h
    WHERE {_EXPLORER_HUB_WHERE}
    ORDER BY h.iata COLLATE NOCASE
"""

SQL_EXPLORER_HUBS_WITH_META = f"""
    SELECT h.iata AS iata,
           COALESCE(h.name, '') AS name,
           COALESCE(h.country, '') AS country
    FROM v_my_hubs h
    WHERE {_EXPLORER_HUB_WHERE}
    ORDER BY h.iata COLLATE NOCASE
"""

SQL_EXPLORER_HUB_IATAS = f"""
    SELECT h.iata AS iata
    FROM v_my_hubs h
    WHERE {_EXPLORER_HUB_WHERE}
    ORDER BY h.iata COLLATE NOCASE
"""


def delete_hub(conn: sqlite3.Connection, airport_id: int) -> None:
    """
    Remove one hub and all route data where it appears as origin or destination.
    Runs deletes in one transaction, then VACUUM (outside the transaction).
    """
    aid = int(airport_id)
    with conn:
        conn.execute(
            "DELETE FROM route_demands WHERE origin_id = ? OR dest_id = ?",
            (aid, aid),
        )
        conn.execute(
            "DELETE FROM route_aircraft WHERE origin_id = ? OR dest_id = ?",
            (aid, aid),
        )
        conn.execute(
            "DELETE FROM route_aircraft_snapshot WHERE origin_id = ? OR dest_id = ?",
            (aid, aid),
        )
        conn.execute(
            "DELETE FROM my_routes WHERE origin_id = ? OR dest_id = ?",
            (aid, aid),
        )
        conn.execute("DELETE FROM my_hubs WHERE airport_id = ?", (aid,))
    conn.execute("VACUUM")
