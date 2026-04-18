"""HTTP tests for /api/backup and /api/restore."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

import dashboard.db as dbm
import dashboard.services.backup as backup_mod
from dashboard.server import app
from tests.test_backup import _cleanup_zip, _seed_ops_db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api_backup_db(tmp_path, monkeypatch):
    db_path = tmp_path / "api_ops.db"
    ul = tmp_path / "api_ul"
    ul.mkdir()
    monkeypatch.setattr(backup_mod, "UPLOAD_DIR", ul)
    _seed_ops_db(db_path, hubs=1, routes=1, fleet_qty=2, game_mode="easy", logo_rel="")
    monkeypatch.setattr(dbm, "DB_PATH", str(db_path))
    from app.state import mark_setup_complete

    mark_setup_complete()
    return db_path


def test_get_api_backup_download(client: TestClient, api_backup_db, monkeypatch) -> None:
    r = client.get("/api/backup")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")
    cd = r.headers.get("content-disposition") or ""
    assert "am4ops-backup-" in cd and ".zip" in cd
    buf = io.BytesIO(r.content)
    with zipfile.ZipFile(buf, "r") as zf:
        assert "am4ops.db" in zf.namelist()
        assert "manifest.json" in zf.namelist()


def test_post_restore_json_success(client: TestClient, api_backup_db, auth_headers, tmp_path, monkeypatch):
    r0 = client.get("/api/backup")
    assert r0.status_code == 200
    zip_bytes = r0.content

    other = tmp_path / "other.db"
    _seed_ops_db(other, hubs=2, routes=3, fleet_qty=5, game_mode="realism", logo_rel="")
    monkeypatch.setattr(dbm, "DB_PATH", str(other))

    files = {"backup_file": ("backup.zip", zip_bytes, "application/zip")}
    r = client.post("/api/restore", files=files, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert "manifest" in body
    assert body["manifest"]["hub_count"] == 1


def test_post_restore_rejects_non_zip(client: TestClient, api_backup_db, auth_headers):
    files = {"backup_file": ("x.txt", b"hello", "text/plain")}
    r = client.post("/api/restore", files=files, headers=auth_headers)
    assert r.status_code == 400


def test_post_restore_requires_auth(client: TestClient, api_backup_db):
    files = {"backup_file": ("b.zip", b"PK\x05\x06" + b"\x00" * 18, "application/zip")}
    r = client.post("/api/restore", files=files)
    assert r.status_code == 401


def test_settings_backup_page_renders(client: TestClient, api_backup_db) -> None:
    r = client.get("/settings/backup")
    assert r.status_code == 200
    assert "Export backup" in r.text
    assert 'href="/api/backup"' in r.text
    assert 'hx-post="/api/restore"' in r.text
