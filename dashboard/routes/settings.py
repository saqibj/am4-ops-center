"""Server-backed settings (SQLite), distinct from browser UI settings."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from dashboard.auth import check_auth_token
from dashboard.db import get_db
from dashboard.server import templates
from database.settings_dao import get_game_mode, set_game_mode

router = APIRouter(tags=["pages"])


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
