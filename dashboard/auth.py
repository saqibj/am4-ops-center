"""Dashboard bearer token for mutating API routes (CSRF-style protection for HTMX POST)."""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request

_printed: bool = False
_generated: str | None = None


def get_dashboard_auth_token() -> str:
    """Return the shared secret sent as ``Authorization: Bearer …`` on POST /api/*."""
    global _printed, _generated
    env = (os.environ.get("AM4_ROUTEMINE_TOKEN") or "").strip()
    if env:
        return env
    if _generated is None:
        _generated = secrets.token_urlsafe(24)
    if not _printed:
        _printed = True
        print(
            "AM4_ROUTEMINE_TOKEN not set. Generated session token:",
            _generated,
            flush=True,
        )
        print(
            "Set AM4_ROUTEMINE_TOKEN in your env to persist it across restarts.",
            flush=True,
        )
    return _generated


def check_auth_token(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    expected = f"Bearer {get_dashboard_auth_token()}"
    if not secrets.compare_digest(auth.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
