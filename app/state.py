"""Setup-completion state stored in SQLite settings table."""

from __future__ import annotations

import sqlite3


def set_state_value(key: str, value: str) -> None:
    from dashboard.db import get_write_conn, current_db_path

    p = current_db_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()

    try:
        conn = get_write_conn()
    except FileNotFoundError:
        return
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_state_value(key: str, default: str | None = None) -> str | None:
    from dashboard.db import get_read_conn

    try:
        conn = get_read_conn()
    except FileNotFoundError:
        return default
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ? LIMIT 1", (key,)
        ).fetchone()
        return str(row["value"]) if row else default
    except sqlite3.OperationalError:
        return default
    finally:
        conn.close()


def is_setup_complete() -> bool:
    val = get_state_value("setup_complete")
    if val is None:
        return False
    return val.strip().lower() == "true"


def mark_setup_complete() -> None:
    set_state_value("setup_complete", "true")


def reset_setup() -> None:
    set_state_value("setup_complete", "false")

