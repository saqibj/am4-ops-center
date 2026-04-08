"""My Routes HTMX and JSON."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.auth import check_auth_token
from dashboard.db import fetch_all, fetch_one, get_db, get_read_db
from dashboard.server import templates

from dashboard.routes.api.shared import _airline_est_profit_from_my_routes, _my_routes_rows

router = APIRouter()


@router.get("/route-exists", response_class=HTMLResponse)
def api_route_exists(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    origin: str = Query("", description="Hub IATA (alias for hub_iata)"),
    dest: str = Query("", description="Destination IATA (alias for destination_iata)"),
    aircraft: str = Query(""),
    hub_iata: str = Query(""),
    destination_iata: str = Query(""),
    num_assigned: int = Query(1, ge=1, le=999),
):
    h = (origin or hub_iata or "").strip()
    d = (dest or destination_iata or "").strip()
    ac = (aircraft or "").strip()
    incomplete = not h or not d or not ac
    if incomplete:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {"incomplete": True, "exists": False},
        )
    if conn is None:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {"incomplete": True, "exists": False},
        )
    try:
        hub = fetch_one(
            conn,
            "SELECT id, iata FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
            [h],
        )
        apd = fetch_one(
            conn,
            "SELECT id, iata FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
            [d],
        )
        acr = fetch_one(
            conn,
            "SELECT id, shortname FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
            [ac],
        )
        if not hub or not apd or not acr:
            return templates.TemplateResponse(
                request,
                "partials/route_exists_hint.html",
                {
                    "incomplete": False,
                    "lookup_failed": True,
                    "exists": False,
                    "hub": h,
                    "dest": d,
                    "aircraft": ac,
                },
            )
        row = fetch_one(
            conn,
            """
            SELECT num_assigned FROM my_routes
            WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
            """,
            [int(hub["id"]), int(apd["id"]), int(acr["id"])],
        )
    except sqlite3.OperationalError:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {"incomplete": True, "exists": False},
        )

    add_n = max(1, min(999, int(num_assigned or 1)))
    if not row:
        return templates.TemplateResponse(
            request,
            "partials/route_exists_hint.html",
            {
                "incomplete": False,
                "exists": False,
                "hub": h,
                "dest": d,
                "aircraft": acr.get("shortname") or ac,
            },
        )
    cur = int(row["num_assigned"] or 0)
    return templates.TemplateResponse(
        request,
        "partials/route_exists_hint.html",
        {
            "incomplete": False,
            "exists": True,
            "hub": hub.get("iata") or h,
            "dest": apd.get("iata") or d,
            "aircraft": acr.get("shortname") or ac,
            "current": cur,
            "adding": add_n,
        },
    )


@router.get("/routes/pair-coverage", response_class=HTMLResponse)
def api_routes_pair_coverage(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    hub_iata: str = Query(""),
    destination_iata: str = Query(""),
):
    hub = hub_iata.strip().upper()
    dest = destination_iata.strip().upper()
    my_rows: list[dict] = []
    extract_rows: list[dict] = []
    if not hub or not dest:
        return templates.TemplateResponse(
            request,
            "partials/route_pair_coverage.html",
            {"hub": hub, "dest": dest, "my_rows": [], "extract_rows": []},
        )
    if conn is None:
        pass
    else:
        try:
            hub_row = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [hub],
            )
            dest_row = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [dest],
            )
            if not hub_row or not dest_row:
                my_rows = []
                extract_rows = []
            else:
                oid, did = int(hub_row["id"]), int(dest_row["id"])
                my_rows = fetch_all(
                    conn,
                    """
                    SELECT ac.shortname AS aircraft, mr.num_assigned, mr.notes
                    FROM my_routes mr
                    JOIN aircraft ac ON mr.aircraft_id = ac.id
                    WHERE mr.origin_id = ? AND mr.dest_id = ?
                    ORDER BY ac.shortname COLLATE NOCASE
                    """,
                    [oid, did],
                )
                extract_rows = fetch_all(
                    conn,
                    """
                    SELECT ac.shortname, MAX(ra.profit_per_ac_day) AS profit_per_ac_day
                    FROM route_aircraft ra
                    JOIN aircraft ac ON ra.aircraft_id = ac.id
                    WHERE ra.is_valid = 1 AND ra.origin_id = ? AND ra.dest_id = ?
                    GROUP BY ra.aircraft_id
                    ORDER BY profit_per_ac_day DESC
                    LIMIT 8
                    """,
                    [oid, did],
                )
        except sqlite3.OperationalError:
            pass
    return templates.TemplateResponse(
        request,
        "partials/route_pair_coverage.html",
        {
            "hub": hub,
            "dest": dest,
            "my_rows": my_rows,
            "extract_rows": extract_rows,
        },
    )


@router.get("/routes/inventory", response_class=HTMLResponse)
def api_routes_inventory(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
):
    if conn is None:
        routes = []
    else:
        try:
            routes = _my_routes_rows(conn)
        except sqlite3.OperationalError:
            routes = []
    return templates.TemplateResponse(
        request,
        "partials/my_routes_inventory.html",
        {"routes": routes},
    )


@router.get("/routes/summary", response_class=HTMLResponse)
def api_routes_summary(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
):
    if conn is None:
        row = {"nrows": 0, "assigned": 0}
        est = 0.0
    else:
        try:
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS nrows, COALESCE(SUM(num_assigned), 0) AS assigned
                FROM my_routes
                """,
            )
            est = _airline_est_profit_from_my_routes(conn)
        except sqlite3.OperationalError:
            row = {"nrows": 0, "assigned": 0}
            est = 0.0
    stats = {
        "nrows": int(row["nrows"] or 0) if row else 0,
        "assigned": int(row["assigned"] or 0) if row else 0,
        "est_profit": est,
    }
    return templates.TemplateResponse(
        request,
        "partials/my_routes_summary.html",
        {"stats": stats},
    )


@router.post(
    "/routes/add",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_add(
    request: Request,
    hub_iata: str = Form(""),
    destination_iata: str = Form(""),
    aircraft: str = Form(""),
    num_assigned: int = Form(1),
    notes: str = Form(""),
):
    msg: str | None = None
    try:
        conn = get_db()
        try:
            hub = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [hub_iata.strip()],
            )
            dest = fetch_one(
                conn,
                "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
                [destination_iata.strip()],
            )
            ac = fetch_one(
                conn,
                "SELECT id FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
                [aircraft.strip()],
            )
            if not hub:
                msg = "Unknown hub IATA."
            elif not dest:
                msg = "Unknown destination IATA."
            elif not ac:
                msg = "Unknown aircraft shortname."
            else:
                n = int(num_assigned) if num_assigned else 1
                n = max(1, min(999, n))
                prev = fetch_one(
                    conn,
                    """
                    SELECT num_assigned FROM my_routes
                    WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                    """,
                    [int(hub["id"]), int(dest["id"]), int(ac["id"])],
                )
                conn.execute(
                    """
                    INSERT INTO my_routes (origin_id, dest_id, aircraft_id, num_assigned, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                        num_assigned = MIN(999, my_routes.num_assigned + excluded.num_assigned),
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_routes.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (
                        int(hub["id"]),
                        int(dest["id"]),
                        int(ac["id"]),
                        n,
                        notes.strip() or None,
                    ),
                )
                conn.commit()
                after = fetch_one(
                    conn,
                    """
                    SELECT num_assigned FROM my_routes
                    WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                    """,
                    [int(hub["id"]), int(dest["id"]), int(ac["id"])],
                )
                if prev:
                    msg = (
                        f"Merged +{n} (now {int(after['num_assigned']) if after else n} assigned for "
                        f"{hub_iata.strip().upper()} → {destination_iata.strip().upper()} / {aircraft.strip()})."
                    )
                else:
                    msg = (
                        f"Added {n} × {aircraft.strip()} on "
                        f"{hub_iata.strip().upper()} → {destination_iata.strip().upper()}."
                    )
        finally:
            conn.close()
    except FileNotFoundError:
        msg = "Database not found."
    except sqlite3.OperationalError:
        msg = "Database missing my_routes table — run extract or upgrade schema."

    try:
        c = get_db()
        try:
            routes = _my_routes_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        routes = []
    except sqlite3.OperationalError:
        routes = []

    ctx: dict = {"routes": routes}
    if msg and ("Unknown" in msg or "Database" in msg or "missing" in msg):
        ctx["flash_err"] = msg
    elif msg:
        ctx["flash"] = msg
    elif not ctx.get("flash_err"):
        ctx["flash"] = "Saved route assignment."
    return templates.TemplateResponse(request, "partials/my_routes_inventory.html", ctx)


@router.post(
    "/routes/delete",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_delete(request: Request, my_route_id: int = Form(...)):
    try:
        conn = get_db()
        try:
            conn.execute("DELETE FROM my_routes WHERE id = ?", (int(my_route_id),))
            conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        return templates.TemplateResponse(
            request,
            "partials/my_routes_inventory.html",
            {"routes": [], "flash_err": "Database not found."},
        )

    try:
        c = get_db()
        try:
            routes = _my_routes_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        routes = []
    except sqlite3.OperationalError:
        routes = []
    return templates.TemplateResponse(
        request,
        "partials/my_routes_inventory.html",
        {"routes": routes, "flash": "Removed route row."},
    )


@router.get("/routes/json")
def api_routes_json(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
) -> list[dict]:
    if conn is None:
        return []
    try:
        rows = _my_routes_rows(conn)
    except sqlite3.OperationalError:
        return []
    return [
        {
            "id": r["id"],
            "hub": r["hub"],
            "destination": r["destination"],
            "aircraft": r["aircraft"],
            "num_assigned": r["num_assigned"],
            "notes": r["notes"],
            "profit_per_ac_day": r["profit_per_ac_day"],
            "distance_km": r["distance_km"],
        }
        for r in rows
    ]
