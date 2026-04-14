"""Server-backed settings (SQLite), distinct from browser UI settings."""

from __future__ import annotations

import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dashboard.auth import check_auth_token
from dashboard.db import base_context, get_db
from dashboard.server import templates
from dashboard.services.branding import remove_logo, save_logo, set_airline_name
from database.settings_dao import get_game_mode, set_game_mode

router = APIRouter(tags=["pages"])


def _branding_redirect_response(request: Request, *, err: str | None, ok: str | None) -> Response:
    qs = urlencode({k: v for k, v in (("err", err), ("ok", ok)) if v})
    loc = "/settings/branding" + (f"?{qs}" if qs else "")
    if request.headers.get("hx-request"):
        return Response(status_code=200, headers={"HX-Redirect": loc})
    return RedirectResponse(url=loc, status_code=303)


@router.post("/settings/game-mode", response_class=HTMLResponse)
def post_settings_game_mode(
    request: Request,
    game_mode: str = Form(""),
):
    check_auth_token(request)
    mode = (game_mode or "").strip()
    try:
        conn = get_db()
        try:
            set_game_mode(conn, mode)
            current = get_game_mode(conn)
        finally:
            conn.close()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (FileNotFoundError, sqlite3.Error) as e:
        raise HTTPException(status_code=503, detail=str(e)[:200]) from e

    return templates.TemplateResponse(
        request,
        "partials/game_mode_select.html",
        {"game_mode": current},
    )


@router.get("/settings/branding", response_class=HTMLResponse)
def get_settings_branding(request: Request):
    err = (request.query_params.get("err") or "").strip()
    ok = (request.query_params.get("ok") or "").strip()
    ctx = base_context(request, None)
    ctx["flash_err"] = err or None
    ctx["flash"] = ok or None
    return templates.TemplateResponse(request, "settings/branding.html", ctx)


@router.post("/settings/branding/logo")
async def post_settings_branding_logo(
    request: Request,
    logo: UploadFile = File(...),
):
    check_auth_token(request)
    body = await logo.read()
    filename = logo.filename or "logo"
    try:
        conn = get_db()
        try:
            save_logo(conn, filename=filename, body=body, content_length=None)
        finally:
            conn.close()
    except ValueError as e:
        return _branding_redirect_response(request, err=str(e), ok=None)
    except (FileNotFoundError, sqlite3.Error) as e:
        return _branding_redirect_response(
            request, err=f"Could not save logo: {str(e)[:180]}", ok=None
        )

    return _branding_redirect_response(request, err=None, ok="Logo saved.")


@router.post("/settings/branding/name")
def post_settings_branding_name(
    request: Request,
    airline_name: str = Form(""),
):
    check_auth_token(request)
    try:
        conn = get_db()
        try:
            set_airline_name(conn, airline_name)
        finally:
            conn.close()
    except (FileNotFoundError, sqlite3.Error) as e:
        return _branding_redirect_response(
            request,
            err=f"Could not save name: {str(e)[:180]}",
            ok=None,
        )

    return _branding_redirect_response(request, err=None, ok="Name saved.")


@router.post("/settings/branding/logo/remove")
def post_settings_branding_logo_remove(request: Request):
    check_auth_token(request)
    try:
        conn = get_db()
        try:
            remove_logo(conn)
        finally:
            conn.close()
    except (FileNotFoundError, sqlite3.Error) as e:
        return _branding_redirect_response(
            request, err=f"Could not remove logo: {str(e)[:180]}", ok=None
        )

    return _branding_redirect_response(request, err=None, ok="Logo removed.")
