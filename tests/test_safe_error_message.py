"""SEC-18: sanitized exception text for dashboard flash messages."""

from __future__ import annotations

import sqlite3

from dashboard.errors import safe_error_message


def test_strips_unix_style_path() -> None:
    exc = sqlite3.OperationalError(
        "unable to open database file: /home/user/secrets/am4ops.db"
    )
    out = safe_error_message(exc)
    assert "/home" not in out
    assert "<path>" in out


def test_strips_windows_style_path() -> None:
    exc = Exception(r"failed C:\Users\me\data\am4ops.db")
    out = safe_error_message(exc)
    assert "Users" not in out
    assert "<path>" in out


def test_truncates_long_message() -> None:
    exc = Exception("x" * 300)
    out = safe_error_message(exc)
    assert len(out) == 203
    assert out.endswith("...")


def test_empty_message_uses_default() -> None:
    exc = Exception("   ")
    assert safe_error_message(exc) == "Database error"
