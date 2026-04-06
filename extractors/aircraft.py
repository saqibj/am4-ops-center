"""Dump all valid aircraft from am4 into SQLite."""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)


def extract_all_aircraft(conn: sqlite3.Connection) -> list[dict]:
    """Iterate aircraft IDs and insert valid rows. Call after init()."""
    from am4.utils.aircraft import Aircraft

    rows: list[dict] = []
    n_skipped = 0
    sql = """
    INSERT INTO aircraft (
        id, shortname, name, manufacturer, type, speed, fuel, co2, cost, capacity,
        range_km, rwy, check_cost, maint, speed_mod, fuel_mod, co2_mod, fourx_mod,
        pilots, crew, engineers, technicians, wingspan, length
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    for ac_id in range(0, 500):
        try:
            result = Aircraft.search(str(ac_id))
            ac = result.ac
            if not ac.valid:
                continue
            tup = (
                ac.id,
                ac.shortname,
                ac.name,
                ac.manufacturer,
                ac.type.name,
                float(ac.speed),
                float(ac.fuel),
                float(ac.co2),
                int(ac.cost),
                int(ac.capacity),
                int(ac.range),
                int(ac.rwy),
                int(ac.check_cost),
                int(ac.maint),
                1 if ac.speed_mod else 0,
                1 if ac.fuel_mod else 0,
                1 if ac.co2_mod else 0,
                1 if ac.fourx_mod else 0,
                int(ac.pilots),
                int(ac.crew),
                int(ac.engineers),
                int(ac.technicians),
                int(ac.wingspan),
                int(ac.length),
            )
            conn.execute(sql, tup)
            rows.append(
                {
                    "id": ac.id,
                    "shortname": ac.shortname,
                    "name": ac.name,
                    "type": ac.type.name,
                }
            )
        except Exception as exc:
            n_skipped += 1
            log.warning("skipped aircraft id=%d: %s", ac_id, exc)
            continue
    conn.commit()
    if n_skipped:
        print(f"    ! skipped {n_skipped} aircraft ID lookups due to am4 errors")
    return rows
