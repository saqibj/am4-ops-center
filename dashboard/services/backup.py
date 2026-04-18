"""Backup (export) and restore (import) of the dashboard SQLite database and airline logo."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import APP_VERSION
from dashboard.db import SCHEMA_VERSION, current_db_path, prepare_for_db_file_replacement
from dashboard.services.branding import (
    AIRLINE_LOGO_KEY,
    UPLOAD_DIR,
    ensure_branding_schema,
)
from database.settings_dao import read_game_mode

logger = logging.getLogger(__name__)

ZIP_DB_NAME = "am4ops.db"
MANIFEST_NAME = "manifest.json"
LOGO_ZIP_PREFIX = "logo/"


class BackupError(Exception):
    """Raised when creating a backup archive fails."""


class RestoreError(Exception):
    """Raised when a backup archive is invalid or cannot be restored."""


def _sql_path_literal(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _vacuum_snapshot(source_db_path: Path, dest_path: Path) -> None:
    if dest_path.exists():
        dest_path.unlink()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    esc = _sql_path_literal(dest_path)
    conn = sqlite3.connect(str(source_db_path), timeout=30)
    try:
        conn.execute(f"VACUUM INTO '{esc}'")
    except sqlite3.Error as e:
        raise BackupError(f"Could not snapshot database: {e}") from e
    finally:
        conn.close()


def _count_or_zero(conn: sqlite3.Connection, sql: str) -> int:
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0


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


def _manifest_counts(conn: sqlite3.Connection) -> tuple[int, int, int, str]:
    hubs = _count_or_zero(conn, "SELECT COUNT(*) FROM my_hubs")
    routes = _count_or_zero(
        conn, "SELECT COUNT(*) FROM route_aircraft WHERE is_valid = 1"
    )
    fleet = _count_or_zero(conn, "SELECT COALESCE(SUM(quantity), 0) FROM my_fleet")
    mode = read_game_mode(conn)
    return hubs, routes, fleet, mode


def create_backup(db_path: Path | None = None) -> Path:
    """Create a backup ``.zip`` in a temp directory. Caller serves or moves it and should delete it."""
    src = (db_path or current_db_path()).resolve()
    if not src.is_file():
        raise BackupError(f"Database not found: {src}")

    now = datetime.now(timezone.utc)
    exported_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ts = now.strftime("%Y%m%d-%H%M%S")

    with tempfile.TemporaryDirectory(prefix="am4-backup-") as tdir:
        td = Path(tdir)
        snap = td / "_snapshot.db"
        _vacuum_snapshot(src, snap)

        snap_conn = sqlite3.connect(str(snap))
        try:
            logo_rel = _read_logo_rel(snap_conn)
            hubs, routes, fleet, game_mode = _manifest_counts(snap_conn)
        finally:
            snap_conn.close()

        has_logo = False
        logo_filename: str | None = None
        logo_disk: Path | None = None
        if logo_rel:
            name = Path(logo_rel).name
            if logo_rel == name:
                candidate = (UPLOAD_DIR / name).resolve()
                try:
                    candidate.relative_to(UPLOAD_DIR.resolve())
                except ValueError:
                    candidate = None  # type: ignore[assignment]
                if candidate and candidate.is_file():
                    has_logo = True
                    logo_filename = name
                    logo_disk = candidate
                else:
                    logger.warning(
                        "settings.%s references %r but file is missing on disk; "
                        "backup will omit logo",
                        AIRLINE_LOGO_KEY,
                        name,
                    )

        manifest: dict[str, Any] = {
            "app_version": APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "exported_at": exported_at,
            "game_mode": game_mode,
            "hub_count": hubs,
            "route_count": routes,
            "fleet_count": fleet,
            "has_logo": has_logo,
            "db_filename": ZIP_DB_NAME,
        }
        if has_logo and logo_filename:
            manifest["logo_filename"] = logo_filename

        zip_dir = Path(tempfile.mkdtemp(prefix="am4-backup-"))
        zip_path = zip_dir / f"am4ops-backup-{ts}.zip"
        try:
            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                zf.write(snap, arcname=ZIP_DB_NAME)
                zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n")
                if has_logo and logo_disk and logo_filename:
                    zf.write(logo_disk, arcname=f"{LOGO_ZIP_PREFIX}{logo_filename}")
        except Exception:
            shutil.rmtree(zip_dir, ignore_errors=True)
            raise

    return zip_path


def validate_backup(zip_path: Path) -> dict[str, Any]:
    """Parse and validate ``zip_path``; return the manifest dict."""
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as e:
        raise RestoreError("Invalid or corrupt backup archive.") from e

    with zf:
        names = set(zf.namelist())
        if MANIFEST_NAME not in names:
            raise RestoreError(f"Backup is missing {MANIFEST_NAME}.")
        if ZIP_DB_NAME not in names:
            raise RestoreError(f"Backup is missing {ZIP_DB_NAME}.")

        try:
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RestoreError("manifest.json is not valid JSON.") from e

        required = (
            "app_version",
            "schema_version",
            "exported_at",
            "game_mode",
            "hub_count",
            "route_count",
            "fleet_count",
            "has_logo",
            "db_filename",
        )
        missing = [k for k in required if k not in manifest]
        if missing:
            raise RestoreError(
                "manifest.json is missing required keys: " + ", ".join(missing)
            )

        if manifest.get("has_logo"):
            fn = (manifest.get("logo_filename") or "").strip()
            if not fn:
                raise RestoreError(
                    "Backup manifest declares a logo but logo_filename is missing."
                )
            logo_member = f"{LOGO_ZIP_PREFIX}{fn}"
            if logo_member not in names:
                raise RestoreError(f"Backup is missing {logo_member}.")

    return manifest


def check_compatibility(manifest: dict[str, Any]) -> list[str]:
    """Return warnings; raises ``RestoreError`` if the backup cannot be applied."""
    warnings: list[str] = []
    try:
        backup_schema = int(manifest["schema_version"])
    except (TypeError, ValueError) as e:
        raise RestoreError("manifest schema_version is not a valid integer.") from e

    if backup_schema > SCHEMA_VERSION:
        raise RestoreError(
            "Backup is from a newer version of the app. Please upgrade before restoring."
        )
    if backup_schema < SCHEMA_VERSION:
        warnings.append(
            "Backup is from an older schema version. Migrations will be applied after restore."
        )

    bver = str(manifest.get("app_version") or "").strip()
    if bver and bver != APP_VERSION:
        warnings.append(
            f"Backup app_version is {bver!r} (this app is {APP_VERSION!r})."
        )

    return warnings


def restore_backup(zip_path: Path, db_path: Path | None = None) -> dict[str, Any]:
    """Replace the current database (and optional logo) with the backup. Destructive."""
    manifest = validate_backup(zip_path)
    warnings = check_compatibility(manifest)

    target = (db_path or current_db_path()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    pre_restore = target.parent / f"{target.name}.pre-restore"

    prepare_for_db_file_replacement()

    try:
        if target.is_file():
            shutil.copy2(target, pre_restore)
        else:
            if pre_restore.is_file():
                pre_restore.unlink()

        with tempfile.TemporaryDirectory(prefix="am4-restore-") as tdir:
            td = Path(tdir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extract(ZIP_DB_NAME, path=td)
                extracted_db = td / ZIP_DB_NAME
                if not extracted_db.is_file():
                    raise RestoreError("Extracted database file is missing.")
                shutil.copy2(extracted_db, target)

                if manifest.get("has_logo") and manifest.get("logo_filename"):
                    fn = str(manifest["logo_filename"])
                    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                    member = f"{LOGO_ZIP_PREFIX}{fn}"
                    dest_logo = UPLOAD_DIR / Path(fn).name
                    with zf.open(member) as src, open(dest_logo, "wb") as out:
                        shutil.copyfileobj(src, out)

                    post = sqlite3.connect(str(target), timeout=30)
                    try:
                        ensure_branding_schema(post)
                        post.execute(
                            """
                            INSERT INTO settings (key, value, updated_at)
                            VALUES (?, ?, datetime('now'))
                            ON CONFLICT(key) DO UPDATE SET
                                value = excluded.value,
                                updated_at = datetime('now')
                            """,
                            (AIRLINE_LOGO_KEY, Path(fn).name),
                        )
                        post.commit()
                    finally:
                        post.close()

            if not manifest.get("has_logo"):
                logger.info(
                    "Restored backup has no logo; existing logo file on disk (if any) was left in place."
                )

    except RestoreError:
        raise
    except Exception as e:
        if pre_restore.is_file():
            try:
                shutil.copy2(pre_restore, target)
            except OSError as copy_err:
                logger.error(
                    "Restore failed and could not roll back from pre-restore: %s",
                    copy_err,
                )
        raise RestoreError(f"Restore failed: {e}") from e

    if warnings:
        for w in warnings:
            logger.warning("%s", w)

    out: dict[str, Any] = dict(manifest)
    out["warnings"] = warnings
    return out
