"""My Routes HTMX and JSON."""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.services.fleet_service import (
    available_aircraft_at_hub,
    eligible_aircraft_empty_reason,
    get_eligible_aircraft,
    lookup_route_distance_km,
)
from app.services.route_validator import validate_route
from dashboard.auth import check_auth_token
from dashboard.db import HTML_DB_NOT_FOUND, fetch_all, fetch_one, get_db, get_read_db
from dashboard.server import templates

from database.schema import ensure_my_routes_inventory_schema

from dashboard.routes.api.shared import _airline_est_profit_from_my_routes, _my_routes_rows
from dashboard.services.add_route_undo import (
    consume_undo_token,
    create_undo_token,
    delete_recent_add,
    ensure_route_add_undos_schema,
    get_recent_add_row,
    list_recent_adds,
)

router = APIRouter()


def _referer_is_add_route_page(request: Request) -> bool:
    ref = (request.headers.get("referer") or "")
    return "/routes/add" in ref


def _parse_optional_int_field(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_inline_fleet_quantity(raw: str) -> int:
    v = _parse_optional_int_field(raw)
    if v is None:
        return 0
    return max(0, min(999, v))


def _validate_route_config_from_form(
    route_config_y: str,
    route_config_j: str,
    route_config_f: str,
    route_cargo_l: str,
    route_cargo_h: str,
) -> dict[str, int]:
    cfg: dict[str, int] = {}
    for key, raw in (
        ("config_y", route_config_y),
        ("config_j", route_config_j),
        ("config_f", route_config_f),
        ("cargo_l", route_cargo_l),
        ("cargo_h", route_cargo_h),
    ):
        v = _parse_optional_int_field(raw)
        if v is not None:
            cfg[key] = v
    return cfg


def _has_valid_route_aircraft_row(
    conn: sqlite3.Connection, origin_id: int, dest_id: int, aircraft_id: int
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM route_aircraft
        WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
          AND COALESCE(is_valid, 0) = 1
        LIMIT 1
        """,
        (origin_id, dest_id, aircraft_id),
    ).fetchone()
    return row is not None


def _aircraft_catalog_for_options(conn: sqlite3.Connection | None) -> list[dict]:
    if conn is None:
        return []
    try:
        return fetch_all(
            conn,
            """
            SELECT shortname, name, type, cost,
                   COALESCE(fuel_mod, 0) AS fuel_mod,
                   COALESCE(co2_mod, 0) AS co2_mod,
                   COALESCE(speed_mod, 0) AS speed_mod
            FROM aircraft
            ORDER BY shortname COLLATE NOCASE
            """,
        )
    except sqlite3.OperationalError:
        return []


def _aircraft_meta_json(rows: list[dict]) -> str:
    out: dict[str, dict] = {}
    for r in rows:
        sn = (r.get("shortname") or "").strip().lower()
        if not sn:
            continue
        out[sn] = {
            "type": (str(r.get("type") or "")).upper(),
            "cost": int(r.get("cost") or 0),
            "fuel_mod": int(r.get("fuel_mod") or 0),
            "co2_mod": int(r.get("co2_mod") or 0),
            "speed_mod": int(r.get("speed_mod") or 0),
        }
    return json.dumps(out)


def _buy_next_deep_link(hub_u: str, dest_u: str, dist: float | None) -> str:
    q: dict[str, str] = {}
    if hub_u:
        q["hub"] = hub_u
    if dest_u:
        q["dest"] = dest_u
    if dist is not None:
        q["distance_km"] = str(int(round(float(dist))))
    if not q:
        return "/buy-next"
    return "/buy-next?" + urlencode(q)


def _eligible_aircraft_response_mode(request: Request) -> str:
    if (request.query_params.get("format") or "").strip().lower() == "json":
        return "json"
    if request.headers.get("HX-Request", "").strip().lower() in ("true", "1"):
        return "html"
    accept = request.headers.get("accept", "")
    parts = [p.strip().split(";")[0].lower() for p in accept.split(",") if p.strip()]
    return "json" if parts and parts[0] == "application/json" else "html"


@router.get("/routes/eligible-aircraft")
def api_routes_eligible_aircraft(
    request: Request,
    conn: sqlite3.Connection | None = Depends(get_read_db),
    hub: str = Query("", description="Origin hub IATA"),
    dest: str = Query("", description="Destination IATA"),
    hub_iata: str = Query("", description="Alias for hub"),
    destination_iata: str = Query("", description="Alias for dest"),
    distance_km: float | None = Query(
        None,
        description="Override route distance in km (otherwise demand, route_aircraft, or haversine)",
    ),
):
    """Eligible ``my_fleet`` aircraft for a candidate hub→dest pair (HTML for HTMX, JSON with format=json)."""
    h = (hub or hub_iata or "").strip()
    d = (dest or destination_iata or "").strip()
    mode = _eligible_aircraft_response_mode(request)
    hub_u = h.upper()
    dest_u = d.upper()
    catalog = _aircraft_catalog_for_options(conn)
    meta_json = (
        _aircraft_meta_json([{k: r[k] for k in r.keys()} for r in catalog])
        if catalog
        else "{}"
    )

    def _ctx(
        *,
        aircraft: list,
        empty_reason: str | None,
        incomplete: bool = False,
        dist: float | None = None,
        error_message: str | None = None,
        aircraft_catalog: list[dict] | None = None,
        form_id: str = "add-route-main",
        aircraft_meta_json: str | None = None,
        buy_next_deep_link: str | None = None,
    ) -> dict:
        cat = aircraft_catalog if aircraft_catalog is not None else catalog
        dlink = (
            buy_next_deep_link
            if buy_next_deep_link is not None
            else _buy_next_deep_link(hub_u, dest_u, dist)
        )
        return {
            "hub": hub_u,
            "dest": dest_u,
            "distance_km": dist,
            "aircraft": aircraft,
            "empty_reason": empty_reason,
            "incomplete": incomplete,
            "error_message": error_message,
            "aircraft_catalog": cat,
            "form_id": form_id,
            "aircraft_meta_json": aircraft_meta_json if aircraft_meta_json is not None else meta_json,
            "buy_next_deep_link": dlink,
        }

    if not h or not d:
        ctx = _ctx(aircraft=[], empty_reason=None, incomplete=True, dist=None)
        if mode == "json":
            return JSONResponse(
                {
                    "hub": hub_u,
                    "dest": dest_u,
                    "distance_km": None,
                    "aircraft": [],
                    "empty_reason": None,
                    "incomplete": True,
                }
            )
        return templates.TemplateResponse(
            request,
            "partials/_aircraft_options.html",
            ctx,
        )

    if conn is None:
        if mode == "json":
            return JSONResponse(
                {
                    "hub": hub_u,
                    "dest": dest_u,
                    "distance_km": None,
                    "aircraft": [],
                    "empty_reason": None,
                    "error": "database_unavailable",
                    "incomplete": False,
                },
                status_code=503,
            )
        return HTMLResponse(HTML_DB_NOT_FOUND)

    try:
        hub_row = fetch_one(
            conn,
            "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
            [h],
        )
        dest_row = fetch_one(
            conn,
            "SELECT id FROM airports WHERE UPPER(TRIM(iata)) = UPPER(TRIM(?)) LIMIT 1",
            [d],
        )
    except sqlite3.OperationalError:
        hub_row = None
        dest_row = None

    if not hub_row or not dest_row:
        msg = "Unknown hub or destination airport code."
        if mode == "json":
            return JSONResponse(
                {
                    "hub": hub_u,
                    "dest": dest_u,
                    "distance_km": None,
                    "aircraft": [],
                    "empty_reason": None,
                    "error": msg,
                    "incomplete": False,
                },
                status_code=422,
            )
        return templates.TemplateResponse(
            request,
            "partials/_aircraft_options.html",
            _ctx(aircraft=[], empty_reason=None, dist=None, error_message=msg),
        )

    oid = int(hub_row["id"])
    did = int(dest_row["id"])
    dist: float | None
    if distance_km is not None:
        dist = float(distance_km)
    else:
        dist = lookup_route_distance_km(conn, oid, did)

    if dist is None:
        reason = (
            f"Could not determine distance from {hub_u} to {dest_u}. "
            "Extract demand or routes for this pair, or pass distance_km as a query parameter."
        )
        if mode == "json":
            return JSONResponse(
                {
                    "hub": hub_u,
                    "dest": dest_u,
                    "distance_km": None,
                    "aircraft": [],
                    "empty_reason": reason,
                    "incomplete": False,
                }
            )
        return templates.TemplateResponse(
            request,
            "partials/_aircraft_options.html",
            _ctx(aircraft=[], empty_reason=reason, dist=None),
        )

    try:
        aircraft = get_eligible_aircraft(conn, h, d, dist)
    except ValueError as exc:
        msg = str(exc)
        if mode == "json":
            return JSONResponse(
                {
                    "hub": hub_u,
                    "dest": dest_u,
                    "distance_km": dist,
                    "aircraft": [],
                    "empty_reason": None,
                    "error": msg,
                    "incomplete": False,
                },
                status_code=422,
            )
        return templates.TemplateResponse(
            request,
            "partials/_aircraft_options.html",
            _ctx(aircraft=[], empty_reason=None, dist=dist, error_message=msg),
        )

    empty_reason = (
        None
        if aircraft
        else eligible_aircraft_empty_reason(conn, hub_u, dest_u, float(dist))
    )

    if mode == "json":
        return JSONResponse(
            {
                "hub": hub_u,
                "dest": dest_u,
                "distance_km": float(dist),
                "aircraft": aircraft,
                "empty_reason": empty_reason,
                "incomplete": False,
            }
        )

    return templates.TemplateResponse(
        request,
        "partials/_aircraft_options.html",
        _ctx(aircraft=aircraft, empty_reason=empty_reason, dist=float(dist)),
    )


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
    highlight: str = Query("", description="Emphasize row with this id"),
    fresh: str = Query("", description="Unused; reserved for future UX hints"),
):
    """``highlight`` / ``fresh`` support query params from the My Routes page (return from add-route)."""
    del fresh  # reserved for future toast/banner behavior
    highlight_route_id: int | None = None
    if highlight.strip().isdigit():
        highlight_route_id = int(highlight.strip())
    if conn is None:
        routes = []
    else:
        try:
            ensure_my_routes_inventory_schema(conn)
            routes = _my_routes_rows(conn)
        except sqlite3.OperationalError:
            routes = []
    return templates.TemplateResponse(
        request,
        "partials/my_routes_inventory.html",
        {
            "routes": routes,
            "highlight_route_id": highlight_route_id,
        },
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
    inline_fleet_quantity: str = Form(""),
    inline_fleet_notes: str = Form(""),
    route_config_y: str = Form(""),
    route_config_j: str = Form(""),
    route_config_f: str = Form(""),
    route_cargo_l: str = Form(""),
    route_cargo_h: str = Form(""),
):
    msg: str | None = None
    use_flash_err = False
    success_route: dict[str, str | int] | None = None
    undo_token: str | None = None
    undo_origin: str = ""
    undo_dest: str = ""
    seconds_remaining: int = 60
    expires_at_ms: int | None = None
    flash_supplement: str | None = None
    try:
        conn = get_db()
        try:
            ensure_my_routes_inventory_schema(conn)
            ensure_route_add_undos_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
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
                hub_id = int(hub["id"])
                dest_id = int(dest["id"])
                ac_id = int(ac["id"])
                fleet_row_before = fetch_one(
                    conn,
                    "SELECT id FROM my_fleet WHERE aircraft_id = ? LIMIT 1",
                    [ac_id],
                )
                iq = _parse_inline_fleet_quantity(inline_fleet_quantity)
                if iq > 0:
                    fn = (inline_fleet_notes or "").strip() or None
                    conn.execute(
                        """
                        INSERT INTO my_fleet (aircraft_id, quantity, notes, updated_at)
                        VALUES (?, ?, ?, datetime('now'))
                        ON CONFLICT(aircraft_id) DO UPDATE SET
                            quantity = MIN(999, my_fleet.quantity + excluded.quantity),
                            notes = CASE
                                WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                                THEN excluded.notes
                                ELSE my_fleet.notes
                            END,
                            updated_at = datetime('now')
                        """,
                        (ac_id, iq, fn),
                    )

                vcfg = _validate_route_config_from_form(
                    route_config_y,
                    route_config_j,
                    route_config_f,
                    route_cargo_l,
                    route_cargo_h,
                )
                vr = validate_route(
                    conn,
                    hub_iata.strip(),
                    destination_iata.strip(),
                    aircraft.strip(),
                    vcfg if vcfg else None,
                )
                if vr["errors"]:
                    msg = "; ".join(vr["errors"])
                    use_flash_err = True
                    conn.rollback()
                else:
                    n = int(num_assigned) if num_assigned else 1
                    n = max(1, min(999, n))
                    avail = available_aircraft_at_hub(conn, hub_id, ac_id)
                    if n > avail:
                        msg = (
                            f"Only {avail} of this aircraft type available at hub "
                            f"{hub_iata.strip().upper()} (fleet minus assignments); cannot assign {n}."
                        )
                        use_flash_err = True
                        conn.rollback()
                    else:
                        prev = fetch_one(
                            conn,
                            """
                            SELECT num_assigned FROM my_routes
                            WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                            """,
                            [hub_id, dest_id, ac_id],
                        )
                        ex_needed = (
                            1
                            if (iq > 0 and not _has_valid_route_aircraft_row(conn, hub_id, dest_id, ac_id))
                            else 0
                        )
                        conn.execute(
                            """
                            INSERT INTO my_routes (
                                origin_id, dest_id, aircraft_id, num_assigned, notes,
                                needs_extraction_refresh, updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                            ON CONFLICT(origin_id, dest_id, aircraft_id) DO UPDATE SET
                                num_assigned = MIN(999, my_routes.num_assigned + excluded.num_assigned),
                                notes = CASE
                                    WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                                    THEN excluded.notes
                                    ELSE my_routes.notes
                                END,
                                needs_extraction_refresh = CASE
                                    WHEN excluded.needs_extraction_refresh = 1 THEN 1
                                    ELSE my_routes.needs_extraction_refresh
                                END,
                                updated_at = datetime('now')
                            """,
                            (
                                hub_id,
                                dest_id,
                                ac_id,
                                n,
                                notes.strip() or None,
                                ex_needed,
                            ),
                        )
                        after = fetch_one(
                            conn,
                            """
                            SELECT num_assigned FROM my_routes
                            WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                            """,
                            [hub_id, dest_id, ac_id],
                        )
                        rid_row = fetch_one(
                            conn,
                            """
                            SELECT id FROM my_routes
                            WHERE origin_id = ? AND dest_id = ? AND aircraft_id = ?
                            """,
                            [hub_id, dest_id, ac_id],
                        )
                        hub_u = hub_iata.strip().upper()
                        dest_u = destination_iata.strip().upper()
                        ac_u = aircraft.strip()
                        if rid_row:
                            rid = int(rid_row["id"])
                            success_route = {
                                "id": rid,
                                "add_another_href": "/routes/add?"
                                + urlencode({"hub": hub_u, "destination": dest_u, "aircraft": ac_u}),
                                "my_routes_href": "/my-routes?"
                                + urlencode({"highlight": str(rid), "fresh": "1"}),
                            }
                        parts: list[str] = []
                        if iq > 0:
                            parts.append(f"Added {iq} × {aircraft.strip()} to fleet.")
                        if prev:
                            parts.append(
                                f"Merged +{n} (now {int(after['num_assigned']) if after else n} assigned for "
                                f"{hub_u} → {dest_u} / {ac_u})."
                            )
                        else:
                            parts.append(f"Added {n} × {ac_u} on {hub_u} → {dest_u}.")
                        if vr["warnings"]:
                            parts.append(" ".join(vr["warnings"]))
                        msg = " ".join(parts)
                        if prev is None and rid_row:
                            fleet_id_for_undo: int | None = None
                            if iq > 0 and fleet_row_before is None:
                                fr = fetch_one(
                                    conn,
                                    "SELECT id FROM my_fleet WHERE aircraft_id = ? LIMIT 1",
                                    [ac_id],
                                )
                                if fr:
                                    fleet_id_for_undo = int(fr["id"])
                            rid = int(rid_row["id"])
                            undo_token = create_undo_token(conn, rid, fleet_id_for_undo)
                            undo_origin = hub_u
                            undo_dest = dest_u
                            exp = fetch_one(
                                conn,
                                """
                                SELECT
                                    CAST(strftime('%s', expires_at) AS INTEGER) AS eu,
                                    CAST(strftime('%s', 'now') AS INTEGER) AS nowu
                                FROM route_add_undos
                                WHERE token = ?
                                """,
                                (undo_token,),
                            )
                            if exp and exp["eu"] is not None and exp["nowu"] is not None:
                                eu = int(exp["eu"])
                                nowu = int(exp["nowu"])
                                seconds_remaining = max(0, eu - nowu)
                                expires_at_ms = eu * 1000
                            supp_only: list[str] = []
                            if iq > 0:
                                supp_only.append(f"Added {iq} × {aircraft.strip()} to fleet.")
                            if vr["warnings"]:
                                supp_only.append(" ".join(vr["warnings"]))
                            flash_supplement = " ".join(supp_only).strip() or None
                            msg = None
                        conn.commit()
            if not hub or not dest or not ac:
                conn.rollback()
        except sqlite3.OperationalError:
            try:
                conn.rollback()
            except sqlite3.OperationalError:
                pass
            raise
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

    ctx: dict = {
        "routes": routes,
        "success_route": success_route,
        "highlight_route_id": None,
    }
    if msg and (
        use_flash_err
        or "Unknown" in msg
        or "Database" in msg
        or "missing" in msg
    ):
        ctx["flash_err"] = msg
    elif undo_token:
        ctx["undo_token"] = undo_token
        ctx["undo_origin"] = undo_origin
        ctx["undo_dest"] = undo_dest
        ctx["seconds_remaining"] = seconds_remaining
        if expires_at_ms is not None:
            ctx["expires_at_ms"] = expires_at_ms
        if flash_supplement:
            ctx["flash_supplement"] = flash_supplement
    elif msg:
        ctx["flash"] = msg
    elif not ctx.get("flash_err"):
        ctx["flash"] = "Saved route assignment."

    recent_adds: list = []
    try:
        c2 = get_db()
        try:
            ensure_route_add_undos_schema(c2)
            recent_adds = list_recent_adds(c2, limit=5)
        finally:
            c2.close()
    except FileNotFoundError:
        recent_adds = []
    ctx["recent_adds"] = recent_adds

    tmpl = "partials/my_routes_inventory.html"
    if _referer_is_add_route_page(request):
        tmpl = "partials/my_routes_inventory_add_route_response.html"
    return templates.TemplateResponse(request, tmpl, ctx)


@router.get(
    "/routes/recent-adds",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_recent_adds(request: Request):
    try:
        conn = get_db()
        try:
            ensure_route_add_undos_schema(conn)
            rows = list_recent_adds(conn, limit=5)
        finally:
            conn.close()
    except FileNotFoundError:
        rows = []
    return templates.TemplateResponse(
        request,
        "partials/recent_adds_strip.html",
        {"recent_adds": rows},
    )


@router.get(
    "/routes/recent-adds/{token}/confirm",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_recent_adds_confirm(request: Request, token: str):
    try:
        conn = get_db()
        try:
            row = get_recent_add_row(conn, token)
        finally:
            conn.close()
    except FileNotFoundError:
        row = None
    if not row:
        return templates.TemplateResponse(
            request,
            "partials/recent_adds_confirm.html",
            {"missing": True, "token": token},
        )
    return templates.TemplateResponse(
        request,
        "partials/recent_adds_confirm.html",
        {"row": row, "missing": False, "token": token},
    )


@router.get(
    "/routes/recent-adds/{token}/row",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_recent_adds_row(request: Request, token: str):
    try:
        conn = get_db()
        try:
            row = get_recent_add_row(conn, token)
        finally:
            conn.close()
    except FileNotFoundError:
        row = None
    if not row:
        return templates.TemplateResponse(
            request,
            "partials/recent_adds_row_gone.html",
            {"token": token},
        )
    return templates.TemplateResponse(
        request,
        "partials/recent_adds_row.html",
        {"row": row},
    )


@router.post(
    "/routes/recent-adds/{token}/delete",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_recent_adds_delete(
    request: Request,
    token: str,
    remove_fleet: str = Form(""),
):
    rf = (remove_fleet or "").strip().lower() in ("on", "true", "1", "yes")
    payload: dict | None = None
    try:
        conn = get_db()
        try:
            payload = delete_recent_add(conn, token, rf)
        finally:
            conn.close()
    except FileNotFoundError:
        pass

    if not payload:
        recent_adds_err: list = []
        try:
            c3 = get_db()
            try:
                ensure_route_add_undos_schema(c3)
                recent_adds_err = list_recent_adds(c3, limit=5)
            finally:
                c3.close()
        except FileNotFoundError:
            recent_adds_err = []
        return templates.TemplateResponse(
            request,
            "partials/recent_adds_delete_result.html",
            {
                "ok": False,
                "message": "Already removed.",
                "recent_adds": recent_adds_err,
            },
        )

    try:
        c = get_db()
        try:
            routes = _my_routes_rows(c)
        finally:
            c.close()
    except FileNotFoundError:
        routes = []

    recent_adds: list = []
    try:
        c2 = get_db()
        try:
            ensure_route_add_undos_schema(c2)
            recent_adds = list_recent_adds(c2, limit=5)
        finally:
            c2.close()
    except FileNotFoundError:
        recent_adds = []

    return templates.TemplateResponse(
        request,
        "partials/recent_adds_delete_result.html",
        {
            "ok": True,
            "message": (
                f"Route {payload['origin']}→{payload['dest']} removed."
                + (" Fleet row removed." if payload.get("fleet_removed") else "")
            ),
            "routes": routes,
            "recent_adds": recent_adds,
            "highlight_route_id": None,
            "success_route": None,
        },
    )


@router.post(
    "/routes/undo/{token}",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_routes_undo(request: Request, token: str):
    feedback: str = "Already undone."
    ok = False
    try:
        conn = get_db()
        try:
            payload = consume_undo_token(conn, token)
            if payload:
                feedback = (
                    f"Route {payload['origin']}→{payload['dest']} removed."
                )
                ok = True
            else:
                expired = fetch_one(
                    conn,
                    """
                    SELECT 1 AS x FROM route_add_undos
                    WHERE token = ? AND expires_at <= datetime('now')
                    """,
                    (token,),
                )
                if expired:
                    feedback = "Undo window expired."
                else:
                    feedback = "Already undone."
        finally:
            conn.close()
    except FileNotFoundError:
        feedback = "Database not found."

    return templates.TemplateResponse(
        request,
        "partials/route_undo_result.html",
        {"undo_feedback": feedback, "undo_ok": ok},
    )


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
            {
                "routes": [],
                "flash_err": "Database not found.",
                "highlight_route_id": None,
            },
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
        {
            "routes": routes,
            "flash": "Removed route row.",
            "highlight_route_id": None,
        },
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
