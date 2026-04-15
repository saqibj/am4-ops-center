"""Fleet helpers: eligible aircraft for a candidate route from a hub."""

from __future__ import annotations

import math
import sqlite3
from typing import Any


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (WGS84 sphere approximation)."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c


def lookup_route_distance_km(
    conn: sqlite3.Connection,
    origin_id: int,
    dest_id: int,
) -> float | None:
    """
    Best-effort distance for an airport pair: demand row, then any ``route_aircraft`` row,
    then haversine from ``airports.lat``/``lng``.
    """
    row = conn.execute(
        "SELECT distance_km FROM route_demands WHERE origin_id = ? AND dest_id = ?",
        (origin_id, dest_id),
    ).fetchone()
    if row is not None and row[0] is not None:
        return float(row[0])

    row = conn.execute(
        """
        SELECT distance_km FROM route_aircraft
        WHERE origin_id = ? AND dest_id = ?
        ORDER BY CASE WHEN is_valid = 1 THEN 0 ELSE 1 END,
                 COALESCE(profit_per_ac_day, -1e12) DESC
        LIMIT 1
        """,
        (origin_id, dest_id),
    ).fetchone()
    if row is not None and row[0] is not None:
        return float(row[0])

    a = conn.execute(
        "SELECT lat, lng FROM airports WHERE id = ?",
        (origin_id,),
    ).fetchone()
    b = conn.execute(
        "SELECT lat, lng FROM airports WHERE id = ?",
        (dest_id,),
    ).fetchone()
    if a is None or b is None:
        return None
    lat1, lon1, lat2, lon2 = a[0], a[1], b[0], b[1]
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    return _haversine_km(float(lat1), float(lon1), float(lat2), float(lon2))


def available_aircraft_at_hub(
    conn: sqlite3.Connection,
    aircraft_id: int,
) -> int:
    """
    Unassigned planes of ``aircraft_id``: ``my_fleet.quantity`` minus
    ``SUM(my_routes.num_assigned)`` across all route origins for that aircraft.

    Fleet quantity is global per aircraft type (no hub column in ``my_fleet``); ``num_assigned``
    totals are global across the network. Returns ``0`` if not in fleet.
    """
    row = conn.execute(
        "SELECT COALESCE(quantity, 0) FROM my_fleet WHERE aircraft_id = ?",
        (aircraft_id,),
    ).fetchone()
    qty = int(row[0] or 0) if row else 0
    row2 = conn.execute(
        """
        SELECT COALESCE(SUM(num_assigned), 0)
        FROM my_routes
        WHERE aircraft_id = ?
        """,
        (aircraft_id,),
    ).fetchone()
    asg = int(row2[0] or 0) if row2 else 0
    return max(0, qty - asg)


def eligible_aircraft_empty_reason(
    conn: sqlite3.Connection,
    hub_iata: str,
    dest_iata: str,
    distance_km: float,
) -> str:
    """Human-readable explanation when ``get_eligible_aircraft`` returns no rows.

    Picks the most specific case: no fleet, all units of every type assigned globally, or
    runway/range blocks every type that still has free units.
    """
    hub = hub_iata.strip().upper()

    hub_row = conn.execute(
        "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = ? LIMIT 1",
        (hub,),
    ).fetchone()
    if hub_row is None:
        return f"No aircraft at {hub} can fly this route (range or runway)."
    hub_id = int(hub_row[0])

    n_fleet = int(conn.execute("SELECT COUNT(*) FROM my_fleet").fetchone()[0] or 0)
    if n_fleet == 0:
        return f"You don't own any aircraft at {hub} yet."

    any_avail_at_hub = False
    for row in conn.execute("SELECT aircraft_id FROM my_fleet"):
        aid = int(row[0])
        if available_aircraft_at_hub(conn, aid) >= 1:
            any_avail_at_hub = True
            break

    if not any_avail_at_hub:
        return (
            "All your aircraft of every type are already assigned to routes "
            f"(nothing remaining for new routes from {hub})."
        )

    return f"No aircraft at {hub} can fly this route (range or runway)."


def get_eligible_aircraft(
    conn: sqlite3.Connection,
    hub_iata: str,
    dest_iata: str,
    distance_km: float,
) -> list[dict[str, Any]]:
    """
    Return aircraft in ``my_fleet`` that can be considered for ``hub_iata`` → ``dest_iata``.

    Filters:

    - Runway: ``aircraft.rwy`` must be ``<=`` both airport ``rwy`` values when those values are
      non-null; if an airport ``rwy`` is null, that endpoint is not used to reject aircraft.
    - Availability: ``my_fleet.quantity - SUM(my_routes.num_assigned)`` for that aircraft type
      across all origins must be > 0 (fleet quantity is global; assignments are global totals).

    Each dict includes ``eligible_direct`` (range covers ``distance_km``) and
    ``eligible_with_stopover`` (true when a direct flight is out of range for the aircraft).
    ``stopover_hint`` is filled from ``route_aircraft`` when present, else a generic message when
    only stopover range applies.

    Raises:
        ValueError: unknown hub or destination IATA.
    """
    hub = hub_iata.strip().upper()
    dest = dest_iata.strip().upper()
    if not hub or not dest:
        raise ValueError("hub and destination IATA are required")

    hub_row = conn.execute(
        "SELECT id, rwy FROM airports WHERE UPPER(TRIM(iata)) = ? LIMIT 1",
        (hub,),
    ).fetchone()
    dest_row = conn.execute(
        "SELECT id, rwy FROM airports WHERE UPPER(TRIM(iata)) = ? LIMIT 1",
        (dest,),
    ).fetchone()
    if hub_row is None:
        raise ValueError(f"Unknown hub IATA: {hub_iata!r}")
    if dest_row is None:
        raise ValueError(f"Unknown destination IATA: {dest_iata!r}")

    hub_id = int(hub_row[0])
    hub_rwy = hub_row[1]
    dest_id = int(dest_row[0])
    dest_rwy = dest_row[1]

    ra_by_ac: dict[int, sqlite3.Row] = {}
    for row in conn.execute(
        """
        SELECT aircraft_id, config_y, config_j, config_f,
               needs_stopover, stopover_iata, total_distance, profit_per_ac_day
        FROM route_aircraft
        WHERE origin_id = ? AND dest_id = ? AND is_valid = 1
        ORDER BY profit_per_ac_day DESC
        """,
        (hub_id, dest_id),
    ):
        aid = int(row["aircraft_id"])
        if aid not in ra_by_ac:
            ra_by_ac[aid] = row

    rows = conn.execute(
        """
        SELECT
            ac.id AS aircraft_id,
            ac.shortname,
            ac.name,
            ac.range_km,
            ac.rwy,
            ac.type AS ac_type,
            ac.capacity,
            mf.quantity AS owned_count,
            COALESCE(assign.assigned_total, 0) AS assigned_total,
            COALESCE(rc.route_count, 0) AS current_route_count
        FROM my_fleet mf
        INNER JOIN aircraft ac ON ac.id = mf.aircraft_id
        LEFT JOIN (
            SELECT aircraft_id, SUM(num_assigned) AS assigned_total
            FROM my_routes
            GROUP BY aircraft_id
        ) assign ON assign.aircraft_id = ac.id
        LEFT JOIN (
            SELECT aircraft_id, COUNT(*) AS route_count
            FROM my_routes
            WHERE origin_id = ?
            GROUP BY aircraft_id
        ) rc ON rc.aircraft_id = ac.id
        WHERE mf.quantity > COALESCE(assign.assigned_total, 0)
        ORDER BY ac.shortname COLLATE NOCASE
        """,
        (hub_id,),
    ).fetchall()

    out: list[dict[str, Any]] = []
    dist = float(distance_km)

    for row in rows:
        ac_id = int(row["aircraft_id"])
        # Authoritative availability (my_fleet − global assignments; matches WHERE above).
        avail_at_hub = available_aircraft_at_hub(conn, ac_id)
        if avail_at_hub < 1:
            continue

        ac_rwy = int(row["rwy"] or 0)
        if hub_rwy is not None and ac_rwy > int(hub_rwy):
            continue
        if dest_rwy is not None and ac_rwy > int(dest_rwy):
            continue

        range_km = int(row["range_km"] or 0)
        eligible_direct = range_km >= dist
        eligible_with_stopover = not eligible_direct

        ra = ra_by_ac.get(ac_id)
        stopover_hint: str | None = None
        if eligible_with_stopover:
            if ra is not None and ra["stopover_iata"]:
                stopover_hint = f"via {ra['stopover_iata']}"
            elif ra is not None and int(ra["needs_stopover"] or 0):
                stopover_hint = "Stopover route exists in extraction data"
            else:
                stopover_hint = "Direct flight out of range; stopover may be required"

        cy = ra["config_y"] if ra is not None else None
        cj = ra["config_j"] if ra is not None else None
        cf = ra["config_f"] if ra is not None else None
        ac_type = (row["ac_type"] or "").upper()
        if ac_type == "CARGO":
            seats_y = int(cy) if cy is not None else None
            seats_j = int(cj) if cj is not None else None
            seats_f = None
            cargo = (
                f"L{seats_y} H{seats_j}"
                if seats_y is not None and seats_j is not None
                else None
            )
            if cy is not None and cj is not None:
                config_summary = f"L{int(cy)} H{int(cj)}"
            else:
                config_summary = "—"
        else:
            seats_y = int(cy) if cy is not None else None
            seats_j = int(cj) if cj is not None else None
            seats_f = int(cf) if cf is not None else None
            cargo = None
            if cy is not None or cj is not None or cf is not None:
                config_summary = (
                    f"Y{int(cy or 0)} J{int(cj or 0)} F{int(cf or 0)}"
                )
            else:
                cap = row["capacity"]
                config_summary = f"capacity {int(cap)}" if cap is not None else "—"

        available = avail_at_hub

        out.append(
            {
                "aircraft_id": ac_id,
                "shortname": row["shortname"],
                "name": row["name"],
                "range_km": range_km,
                "runway_m": ac_rwy,
                "seats_y": seats_y,
                "seats_j": seats_j,
                "seats_f": seats_f,
                "cargo": cargo,
                "available_count": available,
                "current_route_count": int(row["current_route_count"]),
                "config_summary": config_summary,
                "eligible_direct": eligible_direct,
                "eligible_with_stopover": eligible_with_stopover,
                "stopover_hint": stopover_hint,
            }
        )

    return out
