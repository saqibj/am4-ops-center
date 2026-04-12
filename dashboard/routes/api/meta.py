"""HTMX search, stats, hub/aircraft JSON lists."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from app.services.hubs import SQL_EXPLORER_HUBS_WITH_NAMES

from dashboard.db import DB_PATH, fetch_all, fetch_one, get_read_db
from dashboard.server import templates

from dashboard.routes.api.shared import _safe_field_id, _search_term_airports

router = APIRouter()


@router.get("/search/airports", response_class=HTMLResponse)
def api_search_airports(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    q: str = Query(""),
    hub_iata: str = Query(""),
    destination_iata: str = Query(""),
    field_id: str = Query("hub_iata"),
):
    term = _search_term_airports(q, hub_iata, destination_iata)
    if len(term) < 2:
        return HTMLResponse("")
    fid = _safe_field_id(field_id, "hub_iata")
    ut = term.upper()
    lt = term.lower()
    sql = """
        SELECT iata, icao, name, fullname, country
        FROM airports
        WHERE iata IS NOT NULL AND TRIM(iata) != ''
          AND (
            (iata IS NOT NULL AND INSTR(UPPER(iata), ?) > 0)
            OR (icao IS NOT NULL AND TRIM(icao) != '' AND INSTR(UPPER(icao), ?) > 0)
            OR INSTR(LOWER(COALESCE(name, '')), ?) > 0
            OR INSTR(LOWER(COALESCE(fullname, '')), ?) > 0
            OR INSTR(LOWER(COALESCE(country, '')), ?) > 0
          )
        ORDER BY iata COLLATE NOCASE
        LIMIT 25
    """
    if conn is None:
        rows = []
    else:
        rows = fetch_all(conn, sql, [ut, ut, lt, lt, lt])
    return templates.TemplateResponse(
        request,
        "partials/search_airports_results.html",
        {"rows": rows, "field_id": fid},
    )


@router.get("/search/aircraft", response_class=HTMLResponse)
def api_search_aircraft(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    q: str = Query(""),
    aircraft: str = Query(""),
    field_id: str = Query("aircraft_route"),
):
    term = (q or aircraft or "").strip()
    if len(term) < 1:
        return HTMLResponse("")
    fid = _safe_field_id(field_id, "aircraft_route")
    lt = term.lower()
    sql = """
        SELECT shortname, name, type, cost
        FROM aircraft
        WHERE INSTR(LOWER(shortname), ?) > 0
           OR INSTR(LOWER(COALESCE(name, '')), ?) > 0
           OR INSTR(LOWER(COALESCE(type, '')), ?) > 0
        ORDER BY shortname COLLATE NOCASE
        LIMIT 25
    """
    if conn is None:
        rows = []
    else:
        rows = fetch_all(conn, sql, [lt, lt, lt])
    return templates.TemplateResponse(
        request,
        "partials/search_aircraft_results.html",
        {"rows": rows, "field_id": fid},
    )


@router.get("/stats", response_class=HTMLResponse)
def api_stats(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
):
    if conn is None:
        row = {"routes": 0, "hubs": 0, "aircraft": 0, "last_extract": None}
    else:
        row = fetch_one(
            conn,
            """
            SELECT
                (SELECT COUNT(*) FROM route_aircraft WHERE is_valid = 1) AS routes,
                (SELECT COUNT(*) FROM v_my_hubs h
                 WHERE h.is_active = 1 AND h.last_extract_status = 'ok') AS hubs,
                (SELECT COUNT(DISTINCT aircraft_id) FROM route_aircraft WHERE is_valid = 1) AS aircraft,
                (SELECT MAX(extracted_at) FROM route_aircraft WHERE is_valid = 1) AS last_extract
            """,
        )
        if not row:
            row = {"routes": 0, "hubs": 0, "aircraft": 0, "last_extract": None}

    p = Path(DB_PATH)
    db_size = p.stat().st_size if p.exists() else None

    return templates.TemplateResponse(
        request,
        "partials/stats_cards.html",
        {"scope": "global", "stats": row, "db_size_bytes": db_size},
    )


@router.get("/hubs")
def api_hubs(
    conn: sqlite3.Connection | None = Depends(get_read_db),
) -> list[dict]:
    if conn is None:
        return []
    rows = fetch_all(conn, SQL_EXPLORER_HUBS_WITH_NAMES)
    return rows


@router.get("/aircraft-list")
def api_aircraft_list(
    conn: sqlite3.Connection | None = Depends(get_read_db),
) -> list[dict]:
    if conn is None:
        return []
    rows = fetch_all(
        conn,
        "SELECT shortname, name, type, cost FROM aircraft ORDER BY shortname",
    )
    return rows
