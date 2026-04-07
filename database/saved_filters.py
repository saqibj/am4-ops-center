"""Persisted filter presets per dashboard page (URL query strings)."""

from __future__ import annotations

import sqlite3
from typing import Any

MAX_NAME_LEN = 80
MAX_PARAMS_LEN = 8192


def ensure_saved_filters_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            page TEXT NOT NULL,
            params_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, page)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saved_filters_page ON saved_filters(page)"
    )
    conn.commit()


def list_saved_filters(conn: sqlite3.Connection, page: str) -> list[dict[str, Any]]:
    ensure_saved_filters_schema(conn)
    cur = conn.execute(
        """
        SELECT id, name, page, params_json, created_at
        FROM saved_filters
        WHERE page = ?
        ORDER BY name COLLATE NOCASE
        """,
        (page,),
    )
    return [dict(r) for r in cur.fetchall()]


def save_saved_filter(
    conn: sqlite3.Connection, *, page: str, name: str, params_json: str
) -> tuple[bool, str | None]:
    """Insert a row. Returns (ok, error_message)."""
    ensure_saved_filters_schema(conn)
    n = (name or "").strip()
    if not n:
        return False, "Name is required."
    if len(n) > MAX_NAME_LEN:
        return False, f"Name must be at most {MAX_NAME_LEN} characters."
    p = (params_json or "").strip()
    if len(p) > MAX_PARAMS_LEN:
        return False, "Filter data is too long."
    try:
        conn.execute(
            """
            INSERT INTO saved_filters (name, page, params_json)
            VALUES (?, ?, ?)
            """,
            (n, page, p),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return False, f"A saved filter named “{n}” already exists on this page."
    except sqlite3.Error as e:
        return False, str(e)[:200]
    return True, None


def delete_saved_filter(conn: sqlite3.Connection, *, page: str, row_id: int) -> bool:
    ensure_saved_filters_schema(conn)
    cur = conn.execute(
        "DELETE FROM saved_filters WHERE id = ? AND page = ?",
        (row_id, page),
    )
    conn.commit()
    return cur.rowcount > 0
