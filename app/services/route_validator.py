"""Centralized validation for a candidate hub → destination → aircraft route."""

from __future__ import annotations

import sqlite3
from typing import Any, TypedDict

from app.services.fleet_service import lookup_route_distance_km


class RouteValidationResult(TypedDict):
    errors: list[str]
    warnings: list[str]
    stopover_required: bool
    stopover_hint: str | None


def validate_route(
    conn: sqlite3.Connection,
    hub_iata: str,
    dest_iata: str,
    aircraft_shortname: str,
    config: dict[str, Any] | None = None,
) -> RouteValidationResult:
    """
    Validate airports, aircraft, runway fit, range vs distance (and stopover via ``route_aircraft``),
    duplicate ``my_routes`` row (warning), and rough seats vs ``route_demands``.

    ``config`` may include ``config_y``/``config_j``/``config_f`` (pax) or ``cargo_l``/``cargo_h`` (cargo).
    Missing values fall back to the best matching ``route_aircraft`` row when present, then passenger
    ``capacity`` for seat-total heuristics.
    """
    errors: list[str] = []
    warnings: list[str] = []
    stopover_required = False
    stopover_hint: str | None = None

    hub_iata = (hub_iata or "").strip()
    dest_iata = (dest_iata or "").strip()
    sn = (aircraft_shortname or "").strip()
    cfg = dict(config) if config else {}

    if not hub_iata:
        errors.append("Hub IATA is required.")
    if not dest_iata:
        errors.append("Destination IATA is required.")
    if not sn:
        errors.append("Aircraft shortname is required.")
    if errors:
        return {
            "errors": errors,
            "warnings": warnings,
            "stopover_required": False,
            "stopover_hint": None,
        }

    hub = conn.execute(
        "SELECT id, rwy FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
        (hub_iata,),
    ).fetchone()
    dest = conn.execute(
        "SELECT id, rwy FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
        (dest_iata,),
    ).fetchone()
    ac = conn.execute(
        """
        SELECT id, range_km, rwy, type, capacity
        FROM aircraft
        WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (sn,),
    ).fetchone()

    if hub is None:
        errors.append(f"Unknown hub IATA: {hub_iata!r}.")
    if dest is None:
        errors.append(f"Unknown destination IATA: {dest_iata!r}.")
    if ac is None:
        errors.append(f"Unknown aircraft shortname: {sn!r}.")
    if errors:
        return {
            "errors": errors,
            "warnings": warnings,
            "stopover_required": False,
            "stopover_hint": None,
        }

    hub_id = int(hub[0])
    hub_rwy = hub[1]
    dest_id = int(dest[0])
    dest_rwy = dest[1]
    ac_id = int(ac[0])
    range_km = int(ac[1] or 0)
    ac_rwy = int(ac[2] or 0)
    ac_type = (ac[3] or "").strip().upper()
    capacity = ac[4]

    if hub_rwy is not None and ac_rwy > int(hub_rwy):
        errors.append("Aircraft runway requirement exceeds hub runway length.")
    if dest_rwy is not None and ac_rwy > int(dest_rwy):
        errors.append("Aircraft runway requirement exceeds destination runway length.")

    ra_row = conn.execute(
        """
        SELECT needs_stopover, stopover_iata, is_valid, config_y, config_j, config_f
        FROM route_aircraft
        WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
        ORDER BY CASE WHEN is_valid = 1 THEN 0 ELSE 1 END,
                 COALESCE(profit_per_ac_day, -1e12) DESC
        LIMIT 1
        """,
        (hub_id, dest_id, ac_id),
    ).fetchone()

    distance_km = lookup_route_distance_km(conn, hub_id, dest_id)
    dist: float | None = float(distance_km) if distance_km is not None else None

    if dist is None:
        warnings.append("Could not resolve route distance; range and stopover checks were skipped.")
    else:
        ra_valid = ra_row is not None and int(ra_row[2] or 0) == 1
        needs_so = ra_row is not None and int(ra_row[0] or 0) == 1
        so_iata = ra_row[1] if ra_row else None

        if range_km >= dist:
            stopover_required = False
            if ra_valid and needs_so and so_iata:
                stopover_hint = f"Extraction lists stopover via {so_iata} (still within aircraft range)."
        else:
            if ra_valid and needs_so:
                stopover_required = True
                stopover_hint = f"via {so_iata}" if so_iata else "Stopover required per extraction data."
            elif ra_valid:
                errors.append(
                    "Aircraft range is below route distance and extraction does not show a valid stopover."
                )
            else:
                errors.append(
                    "Aircraft range is below route distance and no valid extraction row exists for this triple."
                )

    dup = conn.execute(
        """
        SELECT 1 FROM my_routes
        WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
        LIMIT 1
        """,
        (hub_id, dest_id, ac_id),
    ).fetchone()
    if dup:
        warnings.append(
            "This hub, destination, and aircraft already have a row; saving merges quantities."
        )

    dem = conn.execute(
        """
        SELECT COALESCE(demand_y, 0), COALESCE(demand_j, 0), COALESCE(demand_f, 0)
        FROM route_demands
        WHERE origin_id = ? AND dest_id = ?
        """,
        (hub_id, dest_id),
    ).fetchone()

    ray = raj = raf = None
    if ra_row is not None:
        ray, raj, raf = ra_row[3], ra_row[4], ra_row[5]

    total_units = 0
    if ac_type == "CARGO":
        l_raw = cfg.get("cargo_l")
        h_raw = cfg.get("cargo_h")
        l = int(l_raw) if l_raw is not None else int(ray or 0)
        h = int(h_raw) if h_raw is not None else int(raj or 0)
        total_units = l + h
    else:
        y_raw, j_raw, f_raw = cfg.get("config_y"), cfg.get("config_j"), cfg.get("config_f")
        y = int(y_raw) if y_raw is not None else int(ray or 0)
        j = int(j_raw) if j_raw is not None else int(raj or 0)
        f = int(f_raw) if f_raw is not None else int(raf or 0)
        total_units = y + j + f
        if total_units == 0 and capacity is not None:
            total_units = int(capacity or 0)

    if dem is not None:
        dtot = int(dem[0] or 0) + int(dem[1] or 0) + int(dem[2] or 0)
        if dtot > 0 and total_units > 0 and total_units >= 4 * dtot:
            warnings.append(
                "Configured seats/capacity are much larger than extracted daily demand (Y+J+F); sanity-check loads."
            )

    return {
        "errors": errors,
        "warnings": warnings,
        "stopover_required": stopover_required,
        "stopover_hint": stopover_hint,
    }
