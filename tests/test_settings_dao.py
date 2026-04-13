"""Tests for ``database.settings_dao`` (app ``game_mode`` persistence)."""

from __future__ import annotations

import pytest

from database.schema import create_schema, get_connection, migrate_add_unique_constraints
from database.settings_dao import get_game_mode, set_game_mode


def test_default_game_mode_easy(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    assert get_game_mode(conn) == "easy"
    conn.close()


def test_set_and_get_realism(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    set_game_mode(conn, "realism")
    assert get_game_mode(conn) == "realism"
    set_game_mode(conn, "easy")
    assert get_game_mode(conn) == "easy"
    conn.close()


def test_set_invalid_mode_raises(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    with pytest.raises(ValueError, match="game_mode must be one of"):
        set_game_mode(conn, "hard")
    assert get_game_mode(conn) == "easy"
    conn.close()


def test_migrate_idempotent_app_settings(tmp_path) -> None:
    db = tmp_path / "t.db"
    conn = get_connection(db)
    create_schema(conn)
    conn.close()
    c2 = get_connection(db)
    migrate_add_unique_constraints(c2)
    migrate_add_unique_constraints(c2)
    assert get_game_mode(c2) == "easy"
    set_game_mode(c2, "realism")
    migrate_add_unique_constraints(c2)
    assert get_game_mode(c2) == "realism"
    c2.close()
