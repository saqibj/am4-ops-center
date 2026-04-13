"""App-wide settings persisted in SQLite (single-row ``app_settings``)."""

from __future__ import annotations

import sqlite3

from config import GameMode

_GAME_MODES = frozenset({GameMode.EASY.value, GameMode.REALISM.value})

APP_SETTINGS_SCHEMA_FRAGMENT = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    game_mode TEXT NOT NULL DEFAULT 'easy' CHECK (game_mode IN ('easy', 'realism')),
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO app_settings (id, game_mode, updated_at) VALUES (1, 'easy', datetime('now'));
"""


def ensure_app_settings_schema(conn: sqlite3.Connection) -> None:
    """Create ``app_settings`` and seed row id=1 if missing. Idempotent."""
    conn.executescript(APP_SETTINGS_SCHEMA_FRAGMENT)
    conn.commit()


def read_game_mode(conn: sqlite3.Connection) -> str:
    """Read ``game_mode`` with no commit (safe inside an outer SQLite transaction)."""
    try:
        row = conn.execute(
            "SELECT game_mode FROM app_settings WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return GameMode.EASY.value
    if row is None:
        return GameMode.EASY.value
    return str(row[0])


def get_game_mode(conn: sqlite3.Connection) -> str:
    """Return current ``game_mode`` ('easy' or 'realism')."""
    ensure_app_settings_schema(conn)
    return read_game_mode(conn)


def set_game_mode(conn: sqlite3.Connection, mode: str) -> None:
    """Persist ``game_mode``; raises ``ValueError`` if not easy/realism."""
    if mode not in _GAME_MODES:
        raise ValueError(f"game_mode must be one of {_GAME_MODES}, got {mode!r}")
    ensure_app_settings_schema(conn)
    conn.execute(
        """
        UPDATE app_settings
        SET game_mode = ?, updated_at = datetime('now')
        WHERE id = 1
        """,
        (mode,),
    )
    conn.commit()
