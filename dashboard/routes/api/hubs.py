"""Hub Manager (my_hubs) HTMX."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import UserConfig
from dashboard.auth import check_auth_token
import dashboard.db as dbm
from dashboard.db import fetch_all, fetch_one, get_db
from dashboard.errors import safe_error_message
from dashboard.hub_freshness import STALE_AFTER_DAYS, hub_display_status
from dashboard.server import templates
from database.refresh_jobs import ensure_refresh_jobs_schema

from app.services.hubs import delete_hub

from dashboard.routes.api.shared import (
    _EXTRACTION_BUSY_MSG,
    _release_extraction_lock,
    _stale_cutoff_iso,
    _try_acquire_extraction_lock,
)

router = APIRouter()


def _dashboard_extract_config_from_conn(conn: sqlite3.Connection) -> UserConfig:
    """Load last saved extract UserConfig; merge my_fleet-derived plane count when present."""
    from database.schema import derived_total_planes, load_extract_config

    cfg = UserConfig()
    try:
        loaded = load_extract_config(conn)
        if loaded is not None:
            cfg = loaded
        derived = derived_total_planes(conn)
        if derived is not None:
            cfg.total_planes_owned = derived
    except sqlite3.OperationalError:
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
               (SELECT ra.profit_per_ac_day FROM route_aircraft ra
                WHERE ra.origin_id = h.airport_id AND ra.is_valid = 1
                ORDER BY ra.profit_per_ac_day DESC LIMIT 1) AS best_profit_day
        FROM v_my_hubs h
        ORDER BY h.iata COLLATE NOCASE
        """,
    )


def _refresh_job_row(conn: sqlite3.Connection, job_id: int) -> dict | None:
    row = fetch_one(
        conn,
        """
        SELECT id, hub_iata, status, started_at, completed_at, progress_pct, error_message
        FROM refresh_jobs
        WHERE id = ?
        LIMIT 1
        """,
        [int(job_id)],
    )
    return row


def _refresh_job_update(
    *,
    job_id: int,
    status: str,
    progress_pct: int | None = None,
    error_message: str | None = None,
    completed: bool = False,
) -> None:
    conn = sqlite3.connect(str(dbm.current_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    dbm._apply_pragmas(conn)
    try:
        ensure_refresh_jobs_schema(conn)
        sets = ["status = ?"]
        params: list[object] = [status]
        if progress_pct is not None:
            sets.append("progress_pct = ?")
            params.append(max(0, min(100, int(progress_pct))))
        if error_message is not None:
            sets.append("error_message = ?")
            params.append(error_message[:1024])
        if completed:
            sets.append("completed_at = datetime('now')")
        conn.execute(
            f"UPDATE refresh_jobs SET {', '.join(sets)} WHERE id = ?",
            [*params, int(job_id)],
        )
        conn.commit()
    finally:
        conn.close()


def _run_refresh_job(job_id: int, hub_iata: str) -> None:
    try:
        _refresh_job_update(job_id=job_id, status="running", progress_pct=0)
        _am4_init()
        from extractors.routes import refresh_single_hub

        cfg_conn = sqlite3.connect(str(dbm.current_db_path()), check_same_thread=False)
        cfg_conn.row_factory = sqlite3.Row
        dbm._apply_pragmas(cfg_conn)
        try:
            cfg = _dashboard_extract_config_from_conn(cfg_conn)
        finally:
            cfg_conn.close()

        def _on_progress(done: int, total: int) -> None:
            if total <= 0:
                pct = 100
            else:
                pct = int((max(0, min(done, total)) / total) * 100)
            _refresh_job_update(job_id=job_id, status="running", progress_pct=pct)

        refresh_single_hub(str(dbm.current_db_path()), cfg, hub_iata, _on_progress)
        _refresh_job_update(job_id=job_id, status="completed", progress_pct=100, completed=True)
    except Exception as exc:
        _refresh_job_update(
            job_id=job_id,
            status="failed",
            error_message=safe_error_message(exc),
            completed=True,
        )
    finally:
        _release_extraction_lock()


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
            cfg = _dashboard_extract_config_from_conn(conn)
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
                    VALUES (?, ?, 0, datetime('now'))
                    ON CONFLICT(airport_id) DO UPDATE SET
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
    response_class=JSONResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_hubs_refresh(
    request: Request, background_tasks: BackgroundTasks, hub_id: int = Form(...)
):
    if not _try_acquire_extraction_lock():
        return JSONResponse({"error": _EXTRACTION_BUSY_MSG}, status_code=409)

    def _abort(payload: dict, status_code: int) -> JSONResponse:
        _release_extraction_lock()
        return JSONResponse(payload, status_code=status_code)

    try:
        try:
            conn = get_db()
            try:
                _hubs_ensure_schema(conn)
                ensure_refresh_jobs_schema(conn)
                row = fetch_one(
                    conn,
                    "SELECT iata FROM v_my_hubs WHERE id = ? LIMIT 1",
                    [int(hub_id)],
                )
                if not row or not row.get("iata"):
                    return _abort({"error": "Hub not found."}, 404)
                iata = str(row["iata"]).strip().upper()

                existing = fetch_one(
                    conn,
                    """
                    SELECT id, status
                    FROM refresh_jobs
                    WHERE hub_iata = ?
                      AND status IN ('pending', 'running')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    [iata],
                )
                if existing:
                    return _abort(
                        {
                            "job_id": int(existing["id"]),
                            "status": str(existing["status"]),
                            "error": "Refresh already running for this hub.",
                        },
                        409,
                    )

                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    DELETE FROM refresh_jobs
                    WHERE completed_at IS NOT NULL
                      AND completed_at < datetime('now', '-7 days')
                    """
                )
                cur = conn.execute(
                    """
                    INSERT INTO refresh_jobs (hub_iata, status, progress_pct, error_message)
                    VALUES (?, 'pending', 0, NULL)
                    """,
                    (iata,),
                )
                job_id = int(cur.lastrowid)
                conn.commit()
            finally:
                conn.close()
        except FileNotFoundError:
            return _abort({"error": "Database not found."}, 500)

        background_tasks.add_task(_run_refresh_job, job_id, iata)
        return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)
    except ImportError:
        _release_extraction_lock()
        return JSONResponse({"error": _HUBS_AM4_UNAVAILABLE_MSG}, status_code=500)
    except Exception:
        _release_extraction_lock()
        raise


@router.get(
    "/hubs/refresh/{job_id}",
    response_class=JSONResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_hubs_refresh_status(request: Request, job_id: int):
    try:
        conn = get_db()
        try:
            ensure_refresh_jobs_schema(conn)
            row = _refresh_job_row(conn, int(job_id))
        finally:
            conn.close()
    except FileNotFoundError:
        return JSONResponse({"error": "Database not found."}, status_code=500)
    if row is None:
        return JSONResponse({"error": "Refresh job not found."}, status_code=404)
    return JSONResponse(
        {
            "job_id": int(row["id"]),
            "hub_iata": str(row["hub_iata"]),
            "status": str(row["status"]),
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "progress_pct": int(row["progress_pct"] or 0),
            "error_message": row["error_message"],
        }
    )


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

        try:
            ccfg = get_db()
            try:
                cfg = _dashboard_extract_config_from_conn(ccfg)
            finally:
                ccfg.close()
        except FileNotFoundError:
            cfg = UserConfig()
        errors: list[str] = []
        ok_n = 0
        for row in stale:
            code = (row.get("iata") or "").strip()
            if not code:
                continue
            try:
                refresh_single_hub(dbm.DB_PATH, cfg, code)
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
            row = fetch_one(
                conn,
                "SELECT airport_id FROM my_hubs WHERE id = ? LIMIT 1",
                [int(hub_id)],
            )
            if not row or row.get("airport_id") is None:
                return _hub_inventory_response(request, flash_err="Hub not found.")
            delete_hub(conn, int(row["airport_id"]))
        finally:
            conn.close()
    except FileNotFoundError:
        return _hub_inventory_response(request, flash_err="Database not found.")
    except sqlite3.OperationalError as exc:
        return _hub_inventory_response(request, flash_err=safe_error_message(exc))

    return _hub_inventory_response(request, flash="Removed hub and deleted related route data.")
