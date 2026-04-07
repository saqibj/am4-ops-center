"""Saved filter presets (bookmarks) per page — URL query strings in SQLite."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse

from dashboard.auth import check_auth_token
from dashboard.db import get_db
from dashboard.server import templates
from database.saved_filters import (
    delete_saved_filter,
    list_saved_filters,
    save_saved_filter,
)

router = APIRouter()

ALLOWED_PAGES: frozenset[str] = frozenset(
    {
        "buy-next",
        "buy-next-global",
        "fleet-planner",
        "fleet-health",
        "scenarios",
        "demand-utilization",
        "extraction-deltas",
    }
)

FORM_IDS: dict[str, str] = {
    "buy-next": "buynext-filters",
    "buy-next-global": "buynext-global-filters",
    "fleet-planner": "fleet-filters",
    "fleet-health": "fleet-health-filters",
    "scenarios": "scenario-filters",
    "demand-utilization": "demand-util-filters",
    "extraction-deltas": "ed-filters",
}


def _bar_context(
    request: Request,
    page: str,
    *,
    error: str | None = None,
) -> dict:
    fid = FORM_IDS.get(page, "filters")
    items: list = []
    try:
        conn = get_db()
        try:
            items = list_saved_filters(conn, page)
        finally:
            conn.close()
    except FileNotFoundError:
        pass
    return {
        "request": request,
        "saved_filter_page": page,
        "saved_filter_form_id": fid,
        "saved_filter_items": items,
        "saved_filter_error": error,
    }


@router.get("/saved-filters/bar", response_class=HTMLResponse)
def api_saved_filters_bar(
    request: Request,
    page: str = Query("", min_length=1),
):
    p = (page or "").strip()
    if p not in ALLOWED_PAGES:
        return HTMLResponse("<p class='text-sm text-rose-300'>Invalid page.</p>", status_code=400)
    return templates.TemplateResponse(
        request,
        "partials/saved_filters_bar.html",
        _bar_context(request, p),
    )


@router.post(
    "/saved-filters/save",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_saved_filters_save(
    request: Request,
    page: str = Form(""),
    name: str = Form(""),
    params_json: str = Form(""),
):
    p = (page or "").strip()
    if p not in ALLOWED_PAGES:
        return HTMLResponse("<p class='text-sm text-rose-300'>Invalid page.</p>", status_code=400)
    ok, err = False, "Database not found."
    try:
        conn = get_db()
        try:
            ok, err = save_saved_filter(conn, page=p, name=name, params_json=params_json)
        finally:
            conn.close()
    except FileNotFoundError:
        pass
    if not ok:
        ctx = _bar_context(request, p, error=err or "Could not save.")
        return templates.TemplateResponse(
            request,
            "partials/saved_filters_bar.html",
            ctx,
        )
    return templates.TemplateResponse(
        request,
        "partials/saved_filters_bar.html",
        _bar_context(request, p),
    )


@router.post(
    "/saved-filters/delete",
    response_class=HTMLResponse,
    dependencies=[Depends(check_auth_token)],
)
def api_saved_filters_delete(
    request: Request,
    page: str = Form(""),
    bookmark_id: int = Form(..., ge=1),
):
    p = (page or "").strip()
    if p not in ALLOWED_PAGES:
        return HTMLResponse("<p class='text-sm text-rose-300'>Invalid page.</p>", status_code=400)
    err: str | None = None
    try:
        conn = get_db()
        try:
            if not delete_saved_filter(conn, page=p, row_id=bookmark_id):
                err = "That saved filter was not found."
        finally:
            conn.close()
    except FileNotFoundError:
        err = "Database not found."
    ctx = _bar_context(request, p, error=err)
    return templates.TemplateResponse(
        request,
        "partials/saved_filters_bar.html",
        ctx,
    )
