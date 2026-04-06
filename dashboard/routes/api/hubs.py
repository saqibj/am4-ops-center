"""Hub Manager (my_hubs) HTMX."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from config import UserConfig
from dashboard.auth import check_auth_token
from dashboard.db import DB_PATH, fetch_all, fetch_one, get_db
from dashboard.errors import safe_error_message
from dashboard.hub_freshness import STALE_AFTER_DAYS, hub_display_status
from dashboard.server import templates

from dashboard.routes.api.shared import (
    _EXTRACTION_BUSY_MSG,
    _release_extraction_lock,
    _stale_cutoff_iso,
    _try_acquire_extraction_lock,
)

router = APIRouter()


def _dashboard_extract_config() -> UserConfig:
    """Load last saved extract UserConfig; merge my_fleet-derived plane count when present."""
    from database.schema import derived_total_planes, load_extract_config

    cfg = UserConfig()
    try:
        conn = get_db()
        try:
            loaded = load_extract_config(conn)
            if loaded is not None:
                cfg = loaded
            derived = derived_total_planes(conn)
            if derived is not None:
                cfg.total_planes_owned = derived
        finally:
            conn.close()
    except (FileNotFoundError, sqlite3.OperationalError):
        pass
    return cfg


_HUBS_AM4_UNAVAILABLE_MSG = (
    "The am4 package is not available in this Python environment. "
    "Hub add and refresh need am4 (see README): use Python 3.10–3.12, then "
    "pip install -r requirements.txt. On Windows without a working C++ build, use WSL."
)


def _am4_init() -> None:
    from am4.utils.db import init

    init()


def _hubs_ensure_schema(conn: sqlite3.Connection) -> None:
    from database.schema import create_schema

    create_schema(conn)


def _hub_inventory_rows(conn: sqlite3.Connection) -> list[dict]:
    return fetch_all(
        conn,
        """
        SELECT h.id, h.airport_id, h.iata, h.icao, h.name, h.fullname, h.country,
               h.notes, h.is_active, h.last_extracted_at, h.last_extract_status, h.last_extract_error,
               (SELECT COUNT(*) FROM route_aircraft ra
                WHERE ra.origin_id = h.airport_id AND ra.is_valid = 1) AS route_count,
               (SELECT MAX(ra.profit_per_ac_day) FROM route_aircraft ra
                WHERE ra.origin_id = h.airport_id AND ra.is_valid = 1) AS best_profit_day
        FROM v_my_hubs h
        ORDER BY h.iata COLLATE NOCASE
        """,
    )


def _hub_inventory_response(
    request: Request,
    *,
    flash: str | None = None,
    flash_err: str | None = None,
) -> HTMLResponse:
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            hubs = _hub_inventory_rows(conn)
        finally:
            conn.close()
    except FileNotFoundError:
        hubs = []
        flash_err = flash_err or "Database not found."
    except sqlite3.OperationalError as exc:
        hubs = []
        flash_err = flash_err or f"Database or view missing: {safe_error_message(exc)}"
    for h in hubs:
        h["display_status"] = hub_display_status(
            h.get("last_extract_status"), h.get("last_extracted_at")
        )
    ctx: dict = {"hubs": hubs, "stale_after_days": STALE_AFTER_DAYS}
    if flash:
        ctx["flash"] = flash
    if flash_err:
        ctx["flash_err"] = flash_err
    return templates.TemplateResponse(request, "partials/hub_inventory.html", ctx)


@router.get("/hubs/inventory", response_class=HTMLResponse)
def api_hubs_inventory(request: Request):
    return _hub_inventory_response(request)


@router.get("/hubs/summary", response_class=HTMLResponse)
def api_hubs_summary(request: Request):
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            cutoff = _stale_cutoff_iso()
            row = fetch_one(
                conn,
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active,
                       SUM(CASE
                         WHEN last_extract_status = 'ok' AND NOT (
                           last_extracted_at IS NOT NULL
                           AND TRIM(last_extracted_at) != ''
                           AND datetime(last_extracted_at) IS NOT NULL
                           AND datetime(last_extracted_at) < datetime(?)
                         ) THEN 1 ELSE 0
                       END) AS fresh_ok,
                       SUM(CASE
                         WHEN last_extract_status = 'ok'
                          AND last_extracted_at IS NOT NULL
                          AND TRIM(last_extracted_at) != ''
                          AND datetime(last_extracted_at) IS NOT NULL
                          AND datetime(last_extracted_at) < datetime(?)
                         THEN 1 ELSE 0
                       END) AS stale_n,
                       SUM(CASE
                         WHEN last_extract_status = 'error' THEN 1
                         WHEN last_extract_status = 'running' THEN 1
                         WHEN last_extract_status IS NULL
                           OR TRIM(COALESCE(last_extract_status, '')) = '' THEN 1
                         WHEN last_extract_status NOT IN ('ok', 'error', 'running') THEN 1
                         ELSE 0
                       END) AS other_n
                FROM my_hubs
                """,
                [cutoff, cutoff],
            )
        finally:
            conn.close()
    except FileNotFoundError:
        row = {
            "total": 0,
            "active": 0,
            "fresh_ok": 0,
            "stale_n": 0,
            "other_n": 0,
        }
    except sqlite3.OperationalError:
        row = {
            "total": 0,
            "active": 0,
            "fresh_ok": 0,
            "stale_n": 0,
            "other_n": 0,
        }
    stats = {
        "total": int(row["total"] or 0) if row else 0,
        "active": int(row["active"] or 0) if row else 0,
        "fresh_ok": int(row["fresh_ok"] or 0) if row else 0,
        "stale_n": int(row["stale_n"] or 0) if row else 0,
        "other_n": int(row["other_n"] or 0) if row else 0,
        "stale_after_days": STALE_AFTER_DAYS,
    }
    return templates.TemplateResponse(request, "partials/hub_summary.html", {"stats": stats})


@router.post(
    "/hubs/add",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_hubs_add(request: Request, iata_list: str = Form(""), notes: str = Form("")):
    parts = [p.strip().upper() for p in (iata_list or "").replace(";", ",").split(",") if p.strip()]
    if not parts:
        return _hub_inventory_response(request, flash_err="Enter at least one IATA code.")

    errs: list[str] = []
    n_ok = 0
    notes_val = notes.strip() or None
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            cfg = _dashboard_extract_config()
            _am4_init()
            from extractors.routes import upsert_airport_from_am4

            for iata in parts:
                ap_id, err = upsert_airport_from_am4(conn, cfg, iata)
                if err or ap_id is None:
                    errs.append(f"{iata}: {err or 'unknown error'}")
                    continue
                conn.execute(
                    """
                    INSERT INTO my_hubs (airport_id, notes, is_active, updated_at)
                    VALUES (?, ?, 1, datetime('now'))
                    ON CONFLICT(airport_id) DO UPDATE SET
                        is_active = 1,
                        notes = CASE
                            WHEN excluded.notes IS NOT NULL AND TRIM(excluded.notes) != ''
                            THEN excluded.notes
                            ELSE my_hubs.notes
                        END,
                        updated_at = datetime('now')
                    """,
                    (ap_id, notes_val),
                )
                n_ok += 1
            conn.commit()
        finally:
            conn.close()
    except ImportError:
        return _hub_inventory_response(request, flash_err=_HUBS_AM4_UNAVAILABLE_MSG)
    except FileNotFoundError:
        return _hub_inventory_response(request, flash_err="Database not found.")
    except sqlite3.OperationalError as exc:
        return _hub_inventory_response(request, flash_err=safe_error_message(exc))

    if n_ok == 0:
        return _hub_inventory_response(
            request,
            flash_err="\n".join(errs) if errs else "No hubs could be added.",
        )
    msg = f"Added or updated {n_ok} hub(s)."
    if errs:
        msg += "\n\n" + "\n".join(errs)
        return _hub_inventory_response(request, flash_err=msg)
    return _hub_inventory_response(request, flash=msg)


@router.post(
    "/hubs/refresh",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_hubs_refresh(request: Request, hub_id: int = Form(...)):
    if not _try_acquire_extraction_lock():
        return _hub_inventory_response(request, flash_err=_EXTRACTION_BUSY_MSG)
    try:
        iata: str | None = None
        try:
            conn = get_db()
            try:
                _hubs_ensure_schema(conn)
                row = fetch_one(
                    conn,
                    "SELECT iata FROM v_my_hubs WHERE id = ? LIMIT 1",
                    [int(hub_id)],
                )
                if not row or not row.get("iata"):
                    return _hub_inventory_response(request, flash_err="Hub not found.")
                iata = str(row["iata"]).strip()
            finally:
                conn.close()
        except FileNotFoundError:
            return _hub_inventory_response(request, flash_err="Database not found.")

        try:
            _am4_init()
            from extractors.routes import refresh_single_hub

            refresh_single_hub(DB_PATH, _dashboard_extract_config(), iata)
        except ImportError:
            return _hub_inventory_response(request, flash_err=_HUBS_AM4_UNAVAILABLE_MSG)
        except RuntimeError as exc:
            return _hub_inventory_response(request, flash_err=safe_error_message(exc))
        except ValueError as exc:
            return _hub_inventory_response(request, flash_err=safe_error_message(exc))
        except Exception as exc:
            return _hub_inventory_response(request, flash_err=safe_error_message(exc))

        return _hub_inventory_response(request, flash=f"Refreshed routes for {iata}.")
    finally:
        _release_extraction_lock()


@router.post(
    "/hubs/refresh-stale",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_hubs_refresh_stale(request: Request):
    if not _try_acquire_extraction_lock():
        return _hub_inventory_response(request, flash_err=_EXTRACTION_BUSY_MSG)
    try:
        stale: list[dict] = []
        d = STALE_AFTER_DAYS
        cutoff = _stale_cutoff_iso()
        try:
            conn = get_db()
            try:
                _hubs_ensure_schema(conn)
                stale = fetch_all(
                    conn,
                    """
                    SELECT id, iata FROM v_my_hubs
                    WHERE last_extract_status = 'ok'
                      AND last_extracted_at IS NOT NULL
                      AND TRIM(last_extracted_at) != ''
                      AND datetime(last_extracted_at) IS NOT NULL
                      AND datetime(last_extracted_at) < datetime(?)
                    ORDER BY iata COLLATE NOCASE
                    """,
                    [cutoff],
                )
            finally:
                conn.close()
        except FileNotFoundError:
            return _hub_inventory_response(request, flash_err="Database not found.")
        except sqlite3.OperationalError as exc:
            return _hub_inventory_response(request, flash_err=safe_error_message(exc))

        if not stale:
            return _hub_inventory_response(
                request,
                flash=f"No stale hubs (all OK extracts within {d} days, or use per-hub Refresh for errors).",
            )

        try:
            _am4_init()
            from extractors.routes import refresh_single_hub
        except ImportError:
            return _hub_inventory_response(request, flash_err=_HUBS_AM4_UNAVAILABLE_MSG)

        cfg = _dashboard_extract_config()
        errors: list[str] = []
        ok_n = 0
        for row in stale:
            code = (row.get("iata") or "").strip()
            if not code:
                continue
            try:
                refresh_single_hub(DB_PATH, cfg, code)
                ok_n += 1
            except (RuntimeError, ValueError) as exc:
                errors.append(f"{code}: {safe_error_message(exc)}")
            except Exception as exc:
                errors.append(f"{code}: {safe_error_message(exc)}")

        msg = f"Refreshed {ok_n} stale hub(s) (extract older than {d} days)."
        if errors:
            msg += "\n" + "\n".join(errors)
            return _hub_inventory_response(request, flash_err=msg)
        return _hub_inventory_response(request, flash=msg)
    finally:
        _release_extraction_lock()


@router.post(
    "/hubs/delete",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_hubs_delete(request: Request, hub_id: int = Form(...)):
    try:
        conn = get_db()
        try:
            _hubs_ensure_schema(conn)
            conn.execute("DELETE FROM my_hubs WHERE id = ?", (int(hub_id),))
            conn.commit()
        finally:
            conn.close()
    except FileNotFoundError:
        return _hub_inventory_response(request, flash_err="Database not found.")
    except sqlite3.OperationalError as exc:
        return _hub_inventory_response(request, flash_err=safe_error_message(exc))

    return _hub_inventory_response(request, flash="Removed hub from manager.")
