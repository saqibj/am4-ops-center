"""Unit tests for dashboard.services.branding."""

from __future__ import annotations

import sqlite3

import pytest

from dashboard.services import branding as b

# Minimal bodies that satisfy magic-byte rules
_VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
_VALID_JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32
_VALID_SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'


@pytest.fixture
def branding_conn(tmp_path, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    """In-memory SQLite + uploads dir under tmp."""
    monkeypatch.setattr(b, "UPLOAD_DIR", tmp_path / "uploads")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_validate_accepts_png_jpg_svg_under_limit(branding_conn):
    assert b.validate_upload(filename="a.png", body=_VALID_PNG) == ".png"
    assert b.validate_upload(filename="b.jpg", body=_VALID_JPEG) == ".jpg"
    assert b.validate_upload(filename="c.jpeg", body=_VALID_JPEG) == ".jpg"
    assert b.validate_upload(filename="d.svg", body=_VALID_SVG) == ".svg"


def test_validate_rejects_oversize(branding_conn):
    big = _VALID_PNG + b"x" * (256 * 1024)  # > MAX
    with pytest.raises(ValueError, match="256KB"):
        b.validate_upload(filename="x.png", body=big)
    with pytest.raises(ValueError, match="256KB"):
        b.validate_upload(
            filename="x.png", body=_VALID_PNG, content_length=300_000
        )


def test_validate_rejects_bad_extension(branding_conn):
    with pytest.raises(ValueError, match="PNG"):
        b.validate_upload(filename="x.gif", body=_VALID_PNG)


def test_validate_rejects_magic_mismatch_png_with_jpeg_body(branding_conn):
    with pytest.raises(ValueError, match="PNG"):
        b.validate_upload(filename="logo.png", body=_VALID_JPEG)


def test_save_logo_writes_file_and_updates_settings(
    branding_conn: sqlite3.Connection, tmp_path
):
    b.save_logo(
        branding_conn,
        filename="in.png",
        body=_VALID_PNG,
    )
    out = tmp_path / "uploads" / "airline_logo.png"
    assert out.is_file()
    assert out.read_bytes() == _VALID_PNG
    cur = branding_conn.execute(
        "SELECT value FROM settings WHERE key = ?", (b.AIRLINE_LOGO_KEY,)
    ).fetchone()
    assert cur[0] == "airline_logo.png"


def test_save_logo_deletes_old_when_extension_changes(
    branding_conn: sqlite3.Connection, tmp_path
):
    b.save_logo(branding_conn, filename="a.png", body=_VALID_PNG)
    png = tmp_path / "uploads" / "airline_logo.png"
    assert png.is_file()
    b.save_logo(branding_conn, filename="b.jpg", body=_VALID_JPEG)
    assert not png.is_file()
    jpg = tmp_path / "uploads" / "airline_logo.jpg"
    assert jpg.is_file()


def test_remove_logo_clears_row_and_deletes_file(
    branding_conn: sqlite3.Connection, tmp_path
):
    b.save_logo(branding_conn, filename="a.png", body=_VALID_PNG)
    p = tmp_path / "uploads" / "airline_logo.png"
    assert p.is_file()
    b.remove_logo(branding_conn)
    row = branding_conn.execute(
        "SELECT value FROM settings WHERE key = ?", (b.AIRLINE_LOGO_KEY,)
    ).fetchone()
    assert row[0] == ""
    assert not p.is_file()


def test_get_logo_path_none_when_empty_or_missing_file(
    branding_conn: sqlite3.Connection, tmp_path
):
    assert b.get_logo_path(branding_conn) is None
    b.save_logo(branding_conn, filename="a.png", body=_VALID_PNG)
    p = tmp_path / "uploads" / "airline_logo.png"
    assert b.get_logo_path(branding_conn) == p.resolve()
    p.unlink()
    assert b.get_logo_path(branding_conn) is None
