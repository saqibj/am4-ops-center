"""Setup-completion state stored in SQLite app_state table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _state_db_path() -> Path:
    # Reuse dashboard DB resolution (env override + test monkeypatch support).
    from dashboard.db import current_db_path

    return current_db_path()


def _connect() -> sqlite3.Connection:
    p = _state_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_app_state_schema() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_state(key: str, value: str) -> None:
    ensure_app_state_schema()
    ts = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO app_state(key, value, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, ts),
        )
        conn.commit()
    finally:
        conn.close()


def set_state_value(key: str, value: str) -> None:
    _write_state(key, value)


def get_state_value(key: str, default: str | None = None) -> str | None:
    p = _state_db_path()
    if not p.exists():
        return default
    conn = _connect()
    try:
        try:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ? LIMIT 1", (key,)
            ).fetchone()
        except sqlite3.OperationalError:
            return default
    finally:
        conn.close()
    if row is None:
        return default
    return str(row["value"])


def is_setup_complete() -> bool:
    p = _state_db_path()
    if not p.exists():
        return False
    conn = _connect()
    try:
        try:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = 'setup_complete' LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return False
    finally:
        conn.close()
    if row is None:
        return False
    return str(row["value"]).strip().lower() in {"1", "true", "yes", "on"}


def mark_setup_complete() -> None:
    _write_state("setup_complete", "1")


def reset_setup() -> None:
    _write_state("setup_complete", "0")

