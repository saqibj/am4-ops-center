"""Airline logo file + SQLite settings (key airline_logo_path)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import Request

from dashboard.db import open_read_connection

AIRLINE_LOGO_KEY = "airline_logo_path"
AIRLINE_NAME_KEY = "airline_name"
MAX_AIRLINE_NAME_LEN = 60
MAX_LOGO_BYTES = 256 * 1024

# Resolved dashboard package root (…/dashboard)
_DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = _DASHBOARD_ROOT / "static" / "uploads"

_SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO settings (key, value) VALUES ('airline_logo_path', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('airline_name', '');
"""


def _ensure_settings_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_SETTINGS_DDL)


def ensure_branding_schema(conn: sqlite3.Connection) -> None:
    """Idempotently ensure branding settings schema exists."""
    _ensure_settings_table(conn)


def _read_logo_rel(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (AIRLINE_LOGO_KEY,),
        ).fetchone()
    except sqlite3.OperationalError:
        return ""
    if row is None:
        return ""
    return str(row[0] or "").strip()


def _write_logo_rel(conn: sqlite3.Connection, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = datetime('now')
        """,
        (AIRLINE_LOGO_KEY, value),
    )


def get_airline_name(conn: sqlite3.Connection) -> str:
    """Return stored airline display name, or empty string if unset."""
    _ensure_settings_table(conn)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (AIRLINE_NAME_KEY,),
    ).fetchone()
    if row is None:
        return ""
    return str(row[0] or "").strip()


def set_airline_name(conn: sqlite3.Connection, name: str) -> None:
    """Strip, truncate to ``MAX_AIRLINE_NAME_LEN``, persist in ``settings``."""
    text = (name or "").strip()
    if len(text) > MAX_AIRLINE_NAME_LEN:
        text = text[:MAX_AIRLINE_NAME_LEN]
    _ensure_settings_table(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (AIRLINE_NAME_KEY, text),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def resolve_airline_name(request: Request) -> str | None:
    """Display name for templates, or ``None`` if unset/blank."""
    conn, owns = open_read_connection(request)
    if conn is None:
        return None
    try:
        raw = get_airline_name(conn)
        return raw if raw else None
    finally:
        if owns:
            conn.close()


def validate_upload(
    *,
    filename: str,
    body: bytes,
    content_length: int | None = None,
) -> str:
    """
    Validate name, size, extension, magic bytes.
    Returns normalized extension: ``.png``, ``.jpg``, or ``.svg`` (``.jpeg`` → ``.jpg``).
    """
    if content_length is not None and content_length > MAX_LOGO_BYTES:
        raise ValueError("Logo must be 256KB or smaller.")
    if len(body) > MAX_LOGO_BYTES:
        raise ValueError("Logo must be 256KB or smaller.")

    name = Path(filename or "").name
    suffix = Path(name).suffix.lower()
    ext_map = {".png": ".png", ".jpg": ".jpg", ".jpeg": ".jpg", ".svg": ".svg"}
    if suffix not in ext_map:
        raise ValueError("Only PNG, SVG, or JPG files are allowed.")
    ext = ext_map[suffix]

    if ext == ".png":
        if not body.startswith(b"\x89PNG"):
            raise ValueError("File content does not match PNG format.")
    elif ext == ".jpg":
        if not body.startswith(b"\xff\xd8"):
            raise ValueError("File content does not match JPEG format.")
    elif ext == ".svg":
        b = body.lstrip()
        if b.startswith(b"\xef\xbb\xbf"):
            b = b[3:].lstrip()
        if not (b.startswith(b"<?xml") or b.lower().startswith(b"<svg")):
            raise ValueError("File content does not match SVG format.")

    return ext


def get_logo_path(conn: sqlite3.Connection) -> Path | None:
    """Return absolute path to the logo file, or None if unset or missing on disk."""
    raw = _read_logo_rel(conn)
    if not raw:
        return None
    name = Path(raw).name
    if raw != name:
        return None
    path = (UPLOAD_DIR / name).resolve()
    try:
        path.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


def _logo_url_from_relative(rel: str) -> str:
    return f"/static/uploads/{Path(rel).as_posix()}"


def resolve_airline_logo_url(request: Request) -> str | None:
    """Public static URL for sidebar, or None."""
    conn, owns = open_read_connection(request)
    if conn is None:
        return None
    try:
        p = get_logo_path(conn)
        if p is None:
            return None
        rel = p.relative_to(UPLOAD_DIR.resolve())
        return _logo_url_from_relative(rel.as_posix())
    finally:
        if owns:
            conn.close()


def save_logo(
    conn: sqlite3.Connection,
    *,
    filename: str,
    body: bytes,
    content_length: int | None = None,
) -> str:
    """
    Validate, write ``airline_logo{ext}`` under uploads, update settings in one transaction.
    Returns the stored relative filename (e.g. ``airline_logo.png``).
    """
    ext = validate_upload(
        filename=filename, body=body, content_length=content_length
    )
    rel_new = f"airline_logo{ext}"
    path_new = UPLOAD_DIR / rel_new

    _ensure_settings_table(conn)
    old_rel = _read_logo_rel(conn)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        conn.execute("BEGIN IMMEDIATE")
        if old_rel and Path(old_rel).name != rel_new:
            old_path = UPLOAD_DIR / Path(old_rel).name
            if old_path.is_file():
                old_path.unlink()
        path_new.write_bytes(body)
        _write_logo_rel(conn, rel_new)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        if path_new.is_file():
            try:
                path_new.unlink()
            except OSError:
                pass
        raise

    return rel_new


def remove_logo(conn: sqlite3.Connection) -> None:
    """Clear settings row and delete file if present."""
    _ensure_settings_table(conn)
    old_rel = _read_logo_rel(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _write_logo_rel(conn, "")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if old_rel:
        p = UPLOAD_DIR / old_rel
        if p.is_file():
            p.unlink()
