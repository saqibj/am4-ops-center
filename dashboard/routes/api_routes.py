"""HTMX fragments and JSON API under /api/* (per PRD).

Implementation lives in :mod:`dashboard.routes.api`; this module re-exports
``router`` and test hooks for backward compatibility.
"""

from __future__ import annotations

from dashboard.db import DB_PATH
from dashboard.routes.api import router
from dashboard.routes.api.hubs import _am4_init
from dashboard.routes.api.shared import (
    _EXTRACTION_BUSY_MSG,
    _release_extraction_lock,
    _try_acquire_extraction_lock,
)

__all__ = [
    "DB_PATH",
    "router",
    "_am4_init",
    "_EXTRACTION_BUSY_MSG",
    "_release_extraction_lock",
    "_try_acquire_extraction_lock",
]
