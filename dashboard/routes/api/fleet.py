"""My Fleet HTMX and JSON."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from dashboard.auth import check_auth_token
from dashboard.db import fetch_one, get_db, get_read_db
from dashboard.errors import safe_error_message
from dashboard.server import templates

from dashboard.routes.api.shared import _airline_est_profit_from_my_routes, _my_fleet_rows
from database.schema import ensure_my_fleet_optional_schema

router = APIRouter()


@router.get("/fleet/inventory", response_class=HTMLResponse)
def api_fleet_inventory(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
):
    if conn is None:
        fleets = []
    else:
        try:
            ensure_my_fleet_optional_schema(conn)
            fleets = _my_fleet_rows(conn)
        except sqlite3.OperationalError:
            fleets = []
    return templates.TemplateResponse(
        request,
        "partials/fleet_inventory.html",
        {"fleets": fleets},
    )


@router.get("/fleet/summary", response_class=HTMLResponse)
def api_fleet_summary(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
):
    if conn is None:
        row = {"types": 0, "planes": 0}
        est = 0.0
        route_rows = 0
        val_row = {"fleet_value": 0}
        ag_row = {"assigned_total": 0}
        free_row = {"free_total": 0}
    else:
        try:
            ensure_my_fleet_optional_schema(conn)
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS types, COALESCE(SUM(mf.quantity), 0) AS planes
                FROM my_fleet mf
                """,
            )
            est = _airline_est_profit_from_my_routes(conn)
            rc = fetch_one(conn, "SELECT COUNT(*) AS c FROM my_routes")
            route_rows = int(rc["c"] or 0) if rc else 0
            val_row = fetch_one(
                conn,
                """
                SELECT COALESCE(SUM(mf.quantity * COALESCE(ac.cost, 0)), 0) AS fleet_value
                FROM my_fleet mf
                JOIN aircraft ac ON mf.aircraft_id = ac.id
                """,
            )
            ag_row = fetch_one(
                conn,
                """
                SELECT COALESCE(SUM(num_assigned), 0) AS assigned_total
                FROM my_routes
                """,
            )
            free_row = fetch_one(
                conn,
                """
                SELECT COALESCE(SUM(
                    CASE
                        WHEN mf.quantity > COALESCE(ra.asg, 0)
                        THEN mf.quantity - COALESCE(ra.asg, 0)
                        ELSE 0
                    END
                ), 0) AS free_total
                FROM my_fleet mf
                LEFT JOIN (
                    SELECT aircraft_id, SUM(num_assigned) AS asg
                    FROM my_routes
                    GROUP BY aircraft_id
                ) ra ON ra.aircraft_id = mf.aircraft_id
                """,
            )
        except sqlite3.OperationalError:
            row = {"types": 0, "planes": 0}
            est = 0.0
            route_rows = 0
            val_row = {"fleet_value": 0}
            ag_row = {"assigned_total": 0}
            free_row = {"free_total": 0}
    stats = {
        "types": int(row["types"] or 0) if row else 0,
        "planes": int(row["planes"] or 0) if row else 0,
        "est_profit": est,
        "route_rows": route_rows,
        "fleet_value": float(val_row["fleet_value"] or 0) if val_row else 0.0,
        "assigned_total": int(ag_row["assigned_total"] or 0) if ag_row else 0,
        "free_total": int(free_row["free_total"] or 0) if free_row else 0,
    }
    return templates.TemplateResponse(
        request,
        "partials/fleet_summary.html",
        {"stats": stats},
    )


@router.post(
    "/fleet/add",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_fleet_add(
    request: Request,
    aircraft: str = Form(""),
    quantity: int = Form(1),
    engine: str = Form(""),
    mods: str = Form(""),
    purchase_price: str = Form(""),
    notes: str = Form(""),
):
    msg: str | None = None
    try:
        conn = get_db()
        try:
            ensure_my_fleet_optional_schema(conn)
            ac = fetch_one(
                conn,
                "SELECT id FROM aircraft WHERE LOWER(TRIM(shortname)) = LOWER(TRIM(?)) LIMIT 1",
                [aircraft.strip()],
            )
            if not ac or not ac.get("id"):
                msg = "Unknown aircraft shortname."
            else:
                q = int(quantity) if quantity else 1
                q = max(1, min(999, q))
                pp = None
                pp_raw = (purchase_price or "").strip()
                if pp_raw:
                    pp = max(0, int(pp_raw))
                prev = fetch_one(
                    conn,
                    "SELECT quantity FROM my_fleet WHERE aircraft_id = ?",
                    [int(ac["id"])],
                )
                conn.execute(
                    """
                    INSERT INTO my_fleet (aircraft_id, quantity, engine, mods, purchase_price, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(aircraft_id) DO UPDATE SET
                        quantity = MIN(999, my_fleet.quantity + excluded.quantity),
                        engine = CASE
                            WHEN excluded.engine IS NOT NULL AND TRIM(excluded.engine) != ''
                            THEN excluded.engine
                            ELSE my_fleet.engine
                        END,
                        mods = CASE
                            WHEN excluded.mods IS NOT NULL AND TRIM(excluded.mods) != ''
                            THEN excluded.mods
                            ELSE my_fleet.mods
                        END,
                        purchase_price = COALESCE(excluded.purchase_price, my_fleet.purchase_price),
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_fleet.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (
                        int(ac["id"]),
                        q,
                        (engine or "").strip() or None,
                        (mods or "").strip() or None,
                        pp,
                        notes.strip() or None,
                    ),
                )
                conn.commit()
                after = fetch_one(
                    conn,
                    "SELECT quantity FROM my_fleet WHERE aircraft_id = ?",
                    [int(ac["id"])],
                )
                if prev:
                    msg = f"Merged +{q} (now {int(after['quantity']) if after else q} owned for {aircraft.strip()})."
                else:
                    msg = f"Added {q} × {aircraft.strip()}."
        finally:
            conn.close()
    except FileNotFoundError:
        msg = "Database not found."
    except ValueError:
        msg = "Purchase price must be a whole number."
    except sqlite3.OperationalError:
        msg = "Database missing my_fleet table — run extract or upgrade schema."

    try:
        c = get_db()
        try:
            fleets = _my_fleet_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        fleets = []
    except sqlite3.OperationalError:
        fleets = []

    ctx: dict = {"fleets": fleets}
    if msg and ("Database" in msg or "Unknown" in msg or "missing" in msg):
        ctx["flash_err"] = msg
    elif msg:
        ctx["flash"] = msg
    elif not ctx.get("flash_err"):
        ctx["flash"] = "Saved fleet row."
    return templates.TemplateResponse(request, "partials/fleet_inventory.html", ctx)


@router.post(
    "/fleet/delete",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_fleet_delete(request: Request, fleet_id: int = Form(...)):
    try:
        conn = get_db()
        try:
            conn.execute("DELETE FROM my_fleet WHERE id = ?", (int(fleet_id),))
            conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        return templates.TemplateResponse(
            request,
            "partials/fleet_inventory.html",
            {"fleets": [], "flash_err": "Database not found."},
        )

    try:
        c = get_db()
        try:
            fleets = _my_fleet_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        fleets = []
    except sqlite3.OperationalError:
        fleets = []
    return templates.TemplateResponse(
        request,
        "partials/fleet_inventory.html",
        {"fleets": fleets, "flash": "Removed aircraft type from fleet."},
    )


@router.post(
    "/fleet/{fleet_id}/buy",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_fleet_buy(request: Request, fleet_id: int, add_count: int = Form(1)):
    flash: str | None = None
    flash_err: str | None = None
    try:
        conn = get_db()
        try:
            add = max(1, min(999, int(add_count) if add_count else 1))
            cur = conn.execute(
                """
                UPDATE my_fleet
                SET quantity = MIN(999, quantity + ?), updated_at = datetime('now')
                WHERE id = ?
                """,
                (add, int(fleet_id)),
            )
            if cur.rowcount == 0:
                flash_err = "Fleet row not found."
            else:
                row = fetch_one(
                    conn,
                    "SELECT quantity FROM my_fleet WHERE id = ?",
                    (int(fleet_id),),
                )
                new_q = int(row["quantity"]) if row else 0
                conn.commit()
                flash = f"Bought (now {new_q} owned)."
        finally:
            conn.close()
    except FileNotFoundError:
        flash_err = "Database not found."
    except sqlite3.OperationalError as exc:
        flash_err = safe_error_message(exc)

    try:
        c = get_db()
        try:
            fleets = _my_fleet_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        fleets = []
    except sqlite3.OperationalError:
        fleets = []
    ctx: dict = {"fleets": fleets}
    if flash_err:
        ctx["flash_err"] = flash_err
    elif flash:
        ctx["flash"] = flash
    return templates.TemplateResponse(request, "partials/fleet_inventory.html", ctx)


@router.post(
    "/fleet/{fleet_id}/sell",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_fleet_sell(request: Request, fleet_id: int, sell_count: int = Form(1)):
    flash: str | None = None
    flash_err: str | None = None
    try:
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = fetch_one(
                conn,
                """
                SELECT mf.id, mf.quantity, mf.aircraft_id,
                       (SELECT COALESCE(SUM(num_assigned), 0)
                        FROM my_routes WHERE aircraft_id = mf.aircraft_id) AS assigned_sum
                FROM my_fleet mf
                WHERE mf.id = ?
                """,
                (int(fleet_id),),
            )
            if not row:
                conn.rollback()
                flash_err = "Fleet row not found."
            else:
                qty = int(row["quantity"] or 0)
                assigned = int(row["assigned_sum"] or 0)
                free = max(0, qty - assigned)
                want = max(1, int(sell_count) if sell_count else 1)
                sell_n = min(want, free)
                if free <= 0:
                    conn.rollback()
                    flash_err = "No unassigned aircraft to sell (reduce My Routes assignments first)."
                elif sell_n < want:
                    conn.rollback()
                    flash_err = f"Only {free} unassigned; cannot sell {want}."
                else:
                    new_q = qty - sell_n
                    if new_q <= 0:
                        conn.execute("DELETE FROM my_fleet WHERE id = ?", (int(fleet_id),))
                        flash = f"Sold all {qty}; removed type from fleet."
                    else:
                        conn.execute(
                            """
                            UPDATE my_fleet
                            SET quantity = ?, updated_at = datetime('now')
                            WHERE id = ?
                            """,
                            (new_q, int(fleet_id)),
                        )
                        flash = f"Sold {sell_n} (now {new_q} owned)."
                    conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        flash_err = "Database not found."
    except sqlite3.OperationalError as exc:
        flash_err = safe_error_message(exc)

    try:
        c = get_db()
        try:
            fleets = _my_fleet_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        fleets = []
    except sqlite3.OperationalError:
        fleets = []
    ctx: dict = {"fleets": fleets}
    if flash_err:
        ctx["flash_err"] = flash_err
    elif flash:
        ctx["flash"] = flash
    return templates.TemplateResponse(request, "partials/fleet_inventory.html", ctx)


@router.get("/fleet/json")
def api_fleet_json(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
) -> list[dict]:
    if conn is None:
        return []
    try:
        ensure_my_fleet_optional_schema(conn)
        rows = _my_fleet_rows(conn)
    except sqlite3.OperationalError:
        return []
    return [
        {
            "id": r["id"],
            "shortname": r["shortname"],
            "ac_name": r["ac_name"],
            "ac_type": r.get("ac_type"),
            "quantity": r["quantity"],
            "engine": r.get("engine"),
            "mods": r.get("mods"),
            "purchase_price": r.get("purchase_price"),
            "assigned": r.get("assigned", 0),
            "free": r.get("free", 0),
            "unit_cost": r.get("unit_cost", 0),
            "total_value": r.get("total_value", 0),
            "notes": r["notes"],
        }
        for r in rows
    ]
