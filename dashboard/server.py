"""FastAPI app: static files, Jinja2, route registration (per PRD)."""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from app.paths import ensure_runtime_dirs, migrate_legacy_repo_db

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent


def _auth_template_context(request: Request) -> dict[str, Any]:
    from dashboard.auth import get_dashboard_auth_token

    return {"auth_token": get_dashboard_auth_token()}


def _branding_template_context(request: Request) -> dict[str, Any]:
    from dashboard.services.branding import resolve_airline_logo_url, resolve_airline_name

    return {
        "airline_logo_url": resolve_airline_logo_url(request),
        "airline_name": resolve_airline_name(request),
    }


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates"),
    context_processors=[_auth_template_context, _branding_template_context],
)


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    from dashboard.auth import get_dashboard_auth_token
    from dashboard.db import _apply_pragmas, current_db_path, get_read_conn
    from dashboard.services.branding import ensure_branding_schema
    from database.extraction_runs import ensure_extraction_runs_schema
    from database.refresh_jobs import (
        ensure_refresh_jobs_schema,
        mark_orphaned_refresh_jobs_failed,
    )
    from database.saved_filters import ensure_saved_filters_schema
    from database.settings_dao import ensure_app_settings_schema
    from database.schema import apply_route_aircraft_baseline_prices_at_path

    ensure_runtime_dirs()
    if migrate_legacy_repo_db():
        logger.info("Migrated legacy database to %s", current_db_path())

    get_dashboard_auth_token()

    app.state.db_read = None
    app.state.templates = templates

    p = current_db_path()
    if p.is_file():
        def _short_setup_conn() -> sqlite3.Connection:
            c = sqlite3.connect(str(p), check_same_thread=False)
            c.row_factory = sqlite3.Row
            _apply_pragmas(c)
            return c

        try:
            c0 = _short_setup_conn()
            try:
                ensure_extraction_runs_schema(c0)
            finally:
                c0.close()
            logger.info("Schema ensured: extraction_runs")
        except Exception:
            logger.exception("ensure_extraction_runs_schema failed")
            raise

        try:
            c1 = _short_setup_conn()
            try:
                ensure_saved_filters_schema(c1)
            finally:
                c1.close()
            logger.info("Schema ensured: saved_filters")
        except Exception:
            logger.exception("ensure_saved_filters_schema failed")
            raise

        try:
            c1a = _short_setup_conn()
            try:
                ensure_branding_schema(c1a)
            finally:
                c1a.close()
            logger.info("Schema ensured: branding settings")
        except Exception:
            logger.exception("ensure_branding_schema failed")
            raise

        try:
            c1b = _short_setup_conn()
            try:
                ensure_app_settings_schema(c1b)
            finally:
                c1b.close()
            logger.info("Schema ensured: app_settings")
        except Exception:
            logger.exception("ensure_app_settings_schema failed")
            raise

        try:
            c1c = _short_setup_conn()
            try:
                ensure_refresh_jobs_schema(c1c)
                orphaned = mark_orphaned_refresh_jobs_failed(c1c)
                c1c.commit()
            finally:
                c1c.close()
            if orphaned:
                logger.warning("Marked %s orphaned refresh job(s) as failed", orphaned)
            logger.info("Schema ensured: refresh_jobs")
        except Exception:
            logger.exception("ensure_refresh_jobs_schema failed")
            raise

        try:
            elapsed = apply_route_aircraft_baseline_prices_at_path(p)
            if elapsed > 0:
                logger.info("Baseline prices updated in %.1fs", elapsed)
            else:
                logger.info(
                    "Baseline price update skipped (route_aircraft not present yet)"
                )
        except Exception:
            logger.exception("Baseline price update failed")
        else:
            conn = _short_setup_conn()
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM route_aircraft WHERE fuel_price IS NULL OR co2_price IS NULL"
                )
                null_count = int(cur.fetchone()[0])
                total = int(
                    conn.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0]
                )
                if total > 0 and null_count > 0:
                    logger.warning(
                        "%s route_aircraft rows have NULL fuel_price or co2_price — "
                        "run 'python main.py refresh-baseline'",
                        null_count,
                    )
            except sqlite3.OperationalError as e:
                logger.debug("route_aircraft baseline check skipped: %s", e)
            finally:
                conn.close()

        c_read = get_read_conn()
        try:
            jm = c_read.execute("PRAGMA journal_mode").fetchone()
            if not jm or str(jm[0]).lower() != "wal":
                raise RuntimeError(
                    "PRAGMA journal_mode did not return 'wal' (another process may hold the DB in rollback mode). "
                    "Close extract/dashboard/SQL browser and retry."
                )
        finally:
            c_read.close()
        logger.info("SQLite pragmas verified (journal_mode=wal)")

    try:
        yield
    finally:
        app.state.db_read = None
        app.state.db_read_path = None


app = FastAPI(title="AM4 Ops Center Dashboard", lifespan=_app_lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# --- Profiling middleware (always-on request metrics) ---
from dashboard.middleware.profiling import ProfilingMiddleware

if os.environ.get("PROFILE") == "1":
    from dashboard.middleware.profiling import PyInstrumentMiddleware

    app.add_middleware(PyInstrumentMiddleware)

app.add_middleware(ProfilingMiddleware)


@app.middleware("http")
async def setup_redirect_guard(request: Request, call_next):
    from app.state import is_setup_complete

    path = request.url.path
    exempt = (
        path == "/health"
        or path == "/favicon.ico"
        or path.startswith("/static/")
        or path.startswith("/setup")
    )
    if request.method == "GET" and not exempt and path == "/" and not is_setup_complete():
        return RedirectResponse(url="/setup", status_code=307)
    return await call_next(request)


@app.get("/health")
def health() -> JSONResponse:
    from app.state import is_setup_complete

    return JSONResponse({"status": "ok", "setup_complete": is_setup_complete()})


@app.get("/hub", include_in_schema=False)
def redirect_hub():
    return RedirectResponse(url="/hub-explorer", status_code=307)


@app.get("/route", include_in_schema=False)
def redirect_route():
    return RedirectResponse(url="/route-analyzer", status_code=307)


@app.get("/fleet", include_in_schema=False)
def redirect_fleet():
    return RedirectResponse(url="/fleet-planner", status_code=307)


@app.get("/contribution", include_in_schema=False)
def redirect_contribution():
    return RedirectResponse(url="/contributions", status_code=307)


from dashboard.routes import api_routes, pages, setup as setup_routes
from dashboard.routes import settings as settings_routes

app.include_router(pages.router)
app.include_router(settings_routes.router)
app.include_router(setup_routes.router)
app.include_router(api_routes.router)
