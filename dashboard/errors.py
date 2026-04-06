"""User-visible error text sanitization for dashboard HTML (SEC-18)."""

from __future__ import annotations

import re


def safe_error_message(exc: Exception, default: str = "Database error") -> str:
    """Strip filesystem paths from exception text and cap length for UI flash messages."""
    msg = str(exc).strip()
    if not msg:
        return default
    msg = re.sub(r"(/[^\s:'\"]+)+", "<path>", msg)
    msg = re.sub(r"[A-Za-z]:\\[^\s:'\"]+", "<path>", msg)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return msg
