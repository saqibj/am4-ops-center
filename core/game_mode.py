"""Map persisted app settings to AM4 ``User`` / route math inputs."""

from __future__ import annotations

import sqlite3

from database.settings_dao import read_game_mode


def is_realism(conn: sqlite3.Connection) -> bool:
    """True when the DB setting is ``realism`` (contribution uses 1.5× vs easy 1.0×)."""
    return read_game_mode(conn) == "realism"


def as_am4_kwargs(conn: sqlite3.Connection) -> dict[str, bool]:
    """Kwargs aligned with ``am4.utils.game.User.Default(realism=…)`` and ``fourx``."""
    return {
        "realism": is_realism(conn),
        "fourx": False,
    }
