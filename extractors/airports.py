"""Dump all valid airports from am4 into SQLite."""

from __future__ import annotations

import logging
import sqlite3

from config import UserConfig

log = logging.getLogger(__name__)


def extract_all_airports(conn: sqlite3.Connection, config: UserConfig) -> list[dict]:
    """Iterate airport IDs and insert valid rows. Call after init()."""
    from am4.utils.airport import Airport

    rows: list[dict] = []
    n_skipped = 0
    sql = """
    INSERT INTO airports (
        id, iata, icao, name, fullname, country, continent, lat, lng, rwy, rwy_codes,
        market, hub_cost
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    min_rwy = config.min_runway
    for ap_id in range(0, 4500):
        try:
            result = Airport.search(str(ap_id))
            ap = result.ap
            if not ap.valid:
                continue
            if int(ap.rwy) < min_rwy:
                continue
            conn.execute(
                sql,
                (
                    ap.id,
                    ap.iata,
                    ap.icao,
                    ap.name,
                    ap.fullname,
                    ap.country,
                    ap.continent,
                    float(ap.lat),
                    float(ap.lng),
                    int(ap.rwy),
                    ap.rwy_codes,
                    int(ap.market),
                    int(ap.hub_cost),
                ),
            )
            if ap.iata:
                rows.append(
                    {
                        "id": ap.id,
                        "iata": ap.iata,
                        "name": ap.name,
                        "country": ap.country,
                        "rwy": int(ap.rwy),
                    }
                )
        except Exception as exc:
            n_skipped += 1
            log.warning("skipped airport id=%d: %s", ap_id, exc)
            continue
    conn.commit()
    if n_skipped:
        print(f"    ! skipped {n_skipped} airport ID lookups due to am4 errors")
    return rows
