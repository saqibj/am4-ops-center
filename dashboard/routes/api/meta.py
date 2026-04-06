"""HTMX search, stats, hub/aircraft JSON lists."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.db import DB_PATH, fetch_all, get_db
from dashboard.server import templates

from dashboard.routes.api.shared import _safe_field_id, _search_term_airports

router = APIRouter()


@router.get("/search/airports", response_class=HTMLResponse)
def api_search_airports(
    request: Request,
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
    conn = get_db()
    try:
        rows = fetch_all(conn, sql, [ut, ut, lt, lt, lt])
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "partials/search_airports_results.html",
        {"rows": rows, "field_id": fid},
    )


@router.get("/search/aircraft", response_class=HTMLResponse)
def api_search_aircraft(
    request: Request,
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
    conn = get_db()
    try:
        rows = fetch_all(conn, sql, [lt, lt, lt])
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "partials/search_aircraft_results.html",
        {"rows": rows, "field_id": fid},
    )



@router.get("/stats", response_class=HTMLResponse)
def api_stats(request: Request):
    try:
        conn = get_db()
        try:
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS routes,
                       COUNT(DISTINCT origin_id) AS hubs,
                       COUNT(DISTINCT aircraft_id) AS aircraft,
                       MAX(extracted_at) AS last_extract
                FROM route_aircraft WHERE is_valid = 1
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        row = {"routes": 0, "hubs": 0, "aircraft": 0, "last_extract": None}

    from pathlib import Path

    p = Path(DB_PATH)
    db_size = p.stat().st_size if p.exists() else None

    return templates.TemplateResponse(
        request,
        "partials/stats_cards.html",
        {"scope": "global", "stats": row, "db_size_bytes": db_size},
    )


@router.get("/hubs")
def api_hubs() -> list[dict]:
    try:
        conn = get_db()
        try:
            rows = fetch_all(
                conn,
                """
                SELECT DISTINCT a.iata AS iata, a.name AS name
                FROM route_aircraft ra
                JOIN airports a ON ra.origin_id = a.id
                WHERE ra.is_valid = 1 AND a.iata IS NOT NULL AND TRIM(a.iata) != ''
                ORDER BY a.iata
                """,
            )
        finally:
            conn.close()
    except FileNotFoundError:
        rows = []
    return rows


@router.get("/aircraft-list")
def api_aircraft_list() -> list[dict]:
    try:
        conn = get_db()
        try:
            rows = fetch_all(
                conn,
                "SELECT shortname, name, type, cost FROM aircraft ORDER BY shortname",
            )
        finally:
            conn.close()
    except FileNotFoundError:
        rows = []
    return rows
