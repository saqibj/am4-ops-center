"""Unit tests for backup create/restore services."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import dashboard.db as dbm
import dashboard.services.backup as backup_mod
from app import APP_VERSION
from dashboard.db import SCHEMA_VERSION
from dashboard.services.backup import (
    BackupError,
    RestoreError,
    check_compatibility,
    create_backup,
    restore_backup,
    validate_backup,
)
from dashboard.services.branding import AIRLINE_LOGO_KEY, ensure_branding_schema
from database.schema import create_schema, get_connection
from database.settings_dao import ensure_app_settings_schema, set_game_mode


def _seed_ops_db(
    path: Path,
    *,
    hubs: int = 2,
    routes: int = 3,
    fleet_qty: int = 5,
    game_mode: str = "realism",
    logo_rel: str = "",
) -> None:
    conn = get_connection(path)
    create_schema(conn)
    ensure_app_settings_schema(conn)
    set_game_mode(conn, game_mode)
    ensure_branding_schema(conn)
    conn.execute(
        "INSERT INTO airports (id, iata, rwy, lat, lng) VALUES "
        "(1, 'KHI', 3000, 24.86, 67.00), (2, 'DXB', 4000, 25.25, 55.36)"
    )
    conn.execute(
        "INSERT INTO aircraft (id, shortname, name, type, range_km, rwy, capacity) VALUES "
        "(1, 'a1', 'Type one', 'PAX', 8000, 1500, 180), "
        "(2, 'a2', 'Type two', 'PAX', 8000, 1500, 180), "
        "(3, 'a3', 'Type three', 'PAX', 8000, 1500, 180)"
    )
    for i in range(min(hubs, 2)):
        conn.execute(
            "INSERT INTO my_hubs (airport_id) VALUES (?)",
            (i + 1,),
        )
    for r in range(routes):
        aid = (r % 3) + 1
        conn.execute(
            "INSERT INTO route_aircraft (origin_id, dest_id, aircraft_id, distance_km, is_valid) "
            "VALUES (1, 2, ?, 1000, 1)",
            (aid,),
        )
    conn.execute(
        "INSERT INTO my_fleet (aircraft_id, quantity) VALUES (1, ?)", (fleet_qty,)
    )
    if logo_rel:
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
            """,
            (AIRLINE_LOGO_KEY, logo_rel),
        )
    conn.commit()
    conn.close()


def _cleanup_zip(zip_path: Path) -> None:
    if zip_path.is_file():
        zip_path.unlink(missing_ok=True)
    parent = zip_path.parent
    if parent.is_dir() and parent.name.startswith("am4-backup-"):
        import shutil

        shutil.rmtree(parent, ignore_errors=True)


def test_version_constants_importable() -> None:
    assert APP_VERSION and isinstance(APP_VERSION, str)
    assert isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION >= 1


def test_create_backup_zip_contents_with_logo(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "ops.db"
    ul = tmp_path / "uploads"
    ul.mkdir()
    monkeypatch.setattr(backup_mod, "UPLOAD_DIR", ul)
    _seed_ops_db(db_path, logo_rel="")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
    logo_file = ul / "airline_logo.png"
    logo_file.write_bytes(png)
    conn = get_connection(db_path)
    ensure_branding_schema(conn)
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """,
        (AIRLINE_LOGO_KEY, "airline_logo.png"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    zip_path = create_backup(db_path)
    try:
        assert zip_path.is_file()
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "am4ops.db" in names
            assert "manifest.json" in names
            assert "logo/airline_logo.png" in names
            man = json.loads(zf.read("manifest.json").decode())
        assert man["has_logo"] is True
        assert man["hub_count"] == 2
        assert man["route_count"] == 3
        assert man["fleet_count"] == 5
        assert man["game_mode"] == "realism"
        assert man["schema_version"] == SCHEMA_VERSION
    finally:
        _cleanup_zip(zip_path)


def test_create_backup_skips_logo_when_file_missing(tmp_path, monkeypatch, caplog) -> None:
    db_path = tmp_path / "ops2.db"
    ul = tmp_path / "uploads2"
    ul.mkdir()
    monkeypatch.setattr(backup_mod, "UPLOAD_DIR", ul)
    _seed_ops_db(db_path, logo_rel="airline_logo.png")
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    caplog.set_level("WARNING")
    zip_path = create_backup(db_path)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "logo/" not in "".join(names) or "logo/airline_logo.png" not in names
            man = json.loads(zf.read("manifest.json").decode())
        assert man["has_logo"] is False
        assert "missing" in caplog.text.lower() or "references" in caplog.text.lower()
    finally:
        _cleanup_zip(zip_path)


def test_restore_roundtrip(tmp_path, monkeypatch) -> None:
    ul = tmp_path / "uploads3"
    ul.mkdir()
    monkeypatch.setattr(backup_mod, "UPLOAD_DIR", ul)

    db_a = tmp_path / "a.db"
    _seed_ops_db(db_a, hubs=1, routes=2, fleet_qty=3, game_mode="easy")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    (ul / "airline_logo.png").write_bytes(png)
    conn = get_connection(db_a)
    ensure_branding_schema(conn)
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """,
        (AIRLINE_LOGO_KEY, "airline_logo.png"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(dbm, "DB_PATH", str(db_a))
    zip_path = create_backup(db_a)
    try:
        db_b = tmp_path / "b.db"
        _seed_ops_db(db_b, hubs=2, routes=3, fleet_qty=9, game_mode="realism")
        monkeypatch.setattr(dbm, "DB_PATH", str(db_b))

        out = restore_backup(zip_path, db_b)
        assert "warnings" in out
        c = get_connection(db_b)
        try:
            h = c.execute("SELECT COUNT(*) FROM my_hubs").fetchone()[0]
            r = c.execute(
                "SELECT COUNT(*) FROM route_aircraft WHERE is_valid = 1"
            ).fetchone()[0]
            f = c.execute("SELECT COALESCE(SUM(quantity),0) FROM my_fleet").fetchone()[0]
        finally:
            c.close()
        assert int(h) == 1
        assert int(r) == 2
        assert int(f) == 3
        pre = db_b.parent / f"{db_b.name}.pre-restore"
        assert pre.is_file()
    finally:
        _cleanup_zip(zip_path)


def test_validate_and_compatibility_errors(tmp_path) -> None:
    bad = tmp_path / "not.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(RestoreError, match="Invalid|corrupt"):
        validate_backup(bad)

    zpath = tmp_path / "empty.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("readme.txt", "x")
    with pytest.raises(RestoreError, match="manifest"):
        validate_backup(zpath)

    zpath2 = tmp_path / "future.zip"
    with zipfile.ZipFile(zpath2, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "app_version": APP_VERSION,
                    "schema_version": SCHEMA_VERSION + 50,
                    "exported_at": "2026-01-01T00:00:00Z",
                    "game_mode": "easy",
                    "hub_count": 0,
                    "route_count": 0,
                    "fleet_count": 0,
                    "has_logo": False,
                    "db_filename": "am4ops.db",
                }
            ),
        )
        zf.writestr("am4ops.db", b"sqlite")
    man = validate_backup(zpath2)
    with pytest.raises(RestoreError, match="newer"):
        check_compatibility(man)


def test_create_backup_missing_db(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "nope.db"
    monkeypatch.setattr(dbm, "DB_PATH", str(missing))
    with pytest.raises(BackupError, match="not found"):
        create_backup()


def test_check_compatibility_older_schema_warning() -> None:
    man = {
        "app_version": APP_VERSION,
        "schema_version": max(1, SCHEMA_VERSION - 1),
        "exported_at": "x",
        "game_mode": "easy",
        "hub_count": 0,
        "route_count": 0,
        "fleet_count": 0,
        "has_logo": False,
        "db_filename": "am4ops.db",
    }
    w = check_compatibility(man)
    assert any("older schema" in x.lower() for x in w)
