"""First-run setup wizard routes."""

from __future__ import annotations

import csv
import io
import sqlite3

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

import dashboard.db as dbm
from app.credentials import load_credentials, store_credentials
from app.state import (
    get_state_value,
    is_setup_complete,
    mark_setup_complete,
    set_state_value,
)
from commands.airline import _aircraft_id, _norm_keys
from config import UserConfig
from database.schema import create_schema, get_connection
from dashboard.db import base_context, get_read_conn
from dashboard.server import templates
from dashboard.setup_flow import get_progress, start_extraction

router = APIRouter(tags=["setup"])


def _ctx(request: Request, step: int, title: str) -> dict:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_read_conn()
    except FileNotFoundError:
        pass
    ctx = base_context(request, conn)
    if conn is not None:
        conn.close()
    ctx.update(
        {
            "step": step,
            "step_total": 5,
            "step_title": title,
            "setup_complete": is_setup_complete(),
        }
    )
    return ctx


def _parse_hubs(raw: str) -> list[str]:
    return [x.strip().upper() for x in (raw or "").replace(";", ",").split(",") if x.strip()]


@router.get("/setup", response_class=HTMLResponse)
def setup_welcome(request: Request):
    return templates.TemplateResponse(request, "setup/welcome.html", _ctx(request, 1, "Welcome"))


@router.get("/setup/credentials", response_class=HTMLResponse)
def setup_credentials_get(request: Request):
    saved = load_credentials() or {}
    ctx = _ctx(request, 2, "Credentials")
    ctx.update({"saved_token": saved.get("am4_access_token", "")})
    return templates.TemplateResponse(request, "setup/credentials.html", ctx)


@router.post("/setup/credentials", response_class=HTMLResponse)
def setup_credentials_post(request: Request, am4_access_token: str = Form("")):
    token = (am4_access_token or "").strip()
    ctx = _ctx(request, 2, "Credentials")
    if not token:
        ctx["flash_err"] = "Enter an AM4 access token."
        return templates.TemplateResponse(request, "setup/credentials.html", ctx)
    try:
        from am4.utils.db import init

        init()
    except Exception as exc:
        ctx["flash_err"] = f"Credential validation failed: {exc}"
        ctx["saved_token"] = token
        return templates.TemplateResponse(request, "setup/credentials.html", ctx)
    store_credentials({"am4_access_token": token})
    ctx["flash"] = "Credentials validated and stored locally."
    return templates.TemplateResponse(request, "setup/credentials.html", ctx)


@router.get("/setup/hubs", response_class=HTMLResponse)
def setup_hubs_get(request: Request):
    hubs = get_state_value("setup_hubs", "") or ""
    ctx = _ctx(request, 3, "Hub selection")
    ctx["hubs"] = hubs
    return templates.TemplateResponse(request, "setup/hubs.html", ctx)


@router.post("/setup/hubs", response_class=HTMLResponse)
def setup_hubs_post(request: Request, hubs: str = Form("")):
    parsed = _parse_hubs(hubs)
    ctx = _ctx(request, 3, "Hub selection")
    if not parsed:
        ctx["flash_err"] = "Enter at least one IATA hub code."
        ctx["hubs"] = hubs
        return templates.TemplateResponse(request, "setup/hubs.html", ctx)
    set_state_value("setup_hubs", ",".join(parsed))
    ctx["flash"] = f"Saved {len(parsed)} hub(s)."
    ctx["hubs"] = ",".join(parsed)
    return templates.TemplateResponse(request, "setup/hubs.html", ctx)


@router.get("/setup/extract", response_class=HTMLResponse)
def setup_extract_get(request: Request):
    ctx = _ctx(request, 4, "Initial extraction")
    ctx["hubs"] = get_state_value("setup_hubs", "") or ""
    return templates.TemplateResponse(request, "setup/extract.html", ctx)


@router.post("/setup/extract/start", response_class=HTMLResponse)
def setup_extract_start(request: Request):
    hubs = _parse_hubs(get_state_value("setup_hubs", "") or "")
    cfg = UserConfig(hubs=hubs)
    ok, message = start_extraction(str(dbm.current_db_path()), hubs, cfg)
    prog = get_progress()
    return templates.TemplateResponse(
        request,
        "setup/partials/extract_progress.html",
        {"request": request, "progress": prog, "message": message, "started": ok},
    )


@router.get("/setup/extract/progress", response_class=HTMLResponse)
def setup_extract_progress(request: Request):
    prog = get_progress()
    return templates.TemplateResponse(
        request,
        "setup/partials/extract_progress.html",
        {"request": request, "progress": prog, "message": prog.message},
    )


def _import_fleet_csv(db_path: str, text: str) -> tuple[int, list[str]]:
    conn = get_connection(db_path)
    create_schema(conn)
    n_ok = 0
    errs: list[str] = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return 0, ["CSV is empty."]
        for lineno, raw in enumerate(reader, start=2):
            row = _norm_keys(raw)
            sn = row.get("shortname", "")
            if not sn:
                errs.append(f"line {lineno}: missing shortname")
                continue
            try:
                qty = int(row.get("count", "0") or 0)
            except ValueError:
                errs.append(f"line {lineno}: invalid count")
                continue
            if qty < 1:
                errs.append(f"line {lineno}: count must be >= 1")
                continue
            aid = _aircraft_id(conn, sn)
            if aid is None:
                errs.append(f"line {lineno}: unknown aircraft shortname '{sn}'")
                continue
            notes = row.get("notes") or None
            conn.execute(
                """
                INSERT INTO my_fleet (aircraft_id, quantity, notes, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(aircraft_id) DO UPDATE SET
                    quantity = excluded.quantity,
                    notes = COALESCE(excluded.notes, my_fleet.notes),
                    updated_at = datetime('now')
                """,
                (aid, qty, notes),
            )
            n_ok += 1
        conn.commit()
    finally:
        conn.close()
    return n_ok, errs


@router.get("/setup/fleet", response_class=HTMLResponse)
def setup_fleet_get(request: Request):
    ctx = _ctx(request, 5, "Optional fleet import")
    return templates.TemplateResponse(request, "setup/fleet.html", ctx)


@router.post("/setup/fleet", response_class=HTMLResponse)
async def setup_fleet_post(request: Request, file: UploadFile = File(...)):
    ctx = _ctx(request, 5, "Optional fleet import")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        ctx["flash_err"] = "Fleet CSV must be UTF-8 encoded."
        return templates.TemplateResponse(request, "setup/fleet.html", ctx)
    n_ok, errs = _import_fleet_csv(str(dbm.current_db_path()), text)
    if errs:
        ctx["flash_err"] = "Some rows could not be imported."
        ctx["errors"] = errs
    if n_ok:
        ctx["flash"] = f"Imported {n_ok} fleet row(s)."
    return templates.TemplateResponse(request, "setup/fleet.html", ctx)


@router.post("/setup/complete")
def setup_complete(request: Request):
    prog = get_progress()
    if not prog.done or prog.failed or prog.success_hubs < 1:
        return RedirectResponse(url="/setup/extract", status_code=307)
    mark_setup_complete()
    return RedirectResponse(url="/", status_code=307)


@router.get("/setup/rerun")
def setup_rerun(request: Request):
    try:
        conn = dbm.get_write_conn()
        try:
            conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('setup_complete', 'false')
                ON CONFLICT(key) DO UPDATE SET value = 'false'
                """
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
    return RedirectResponse(url="/setup", status_code=303)

