"""Environment variables: prefer ``AM4_OPS_CENTER_*``; fall back to legacy ``AM4_ROUTEMINE_*``."""

from __future__ import annotations

import os

ENV_DB_CANONICAL = "AM4_OPS_CENTER_DB"
ENV_TOKEN_CANONICAL = "AM4_OPS_CENTER_TOKEN"
ENV_DB_LEGACY = "AM4_ROUTEMINE_DB"
ENV_TOKEN_LEGACY = "AM4_ROUTEMINE_TOKEN"


def _strip_or_none(key: str) -> str | None:
    v = (os.environ.get(key) or "").strip()
    return v or None


def resolved_env_db() -> str | None:
    """SQLite path from environment (canonical wins if both are set)."""
    c = _strip_or_none(ENV_DB_CANONICAL)
    if c:
        return c
    return _strip_or_none(ENV_DB_LEGACY)


def resolved_env_token() -> str | None:
    """Bearer token for dashboard mutating APIs (canonical wins if both are set)."""
    c = _strip_or_none(ENV_TOKEN_CANONICAL)
    if c:
        return c
    return _strip_or_none(ENV_TOKEN_LEGACY)


def effective_db_path(fallback: str) -> str:
    """DB path from env, or ``fallback`` (e.g. ``str(db_path())``)."""
    r = resolved_env_db()
    return r if r else fallback


def set_dashboard_db_from_cli(path: str) -> None:
    """If no DB path is already resolved from env, set the canonical variable from ``--db``."""
    if resolved_env_db() is None:
        os.environ[ENV_DB_CANONICAL] = path


def ensure_default_db_env(default_path: str) -> None:
    """If no DB env is set, default the canonical variable (scripts / profiling)."""
    if resolved_env_db() is None:
        os.environ.setdefault(ENV_DB_CANONICAL, default_path)
