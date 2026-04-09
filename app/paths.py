"""Centralized runtime paths for writable application data."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "AM4OpsCenter"
APP_AUTHOR = "am4-ops-center"
DB_FILENAME = "am4ops.db"

_DIRS = PlatformDirs(appname=APP_NAME, appauthor=APP_AUTHOR)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    override = os.environ.get("AM4OPS_DATA_DIR")
    if override:
        return _ensure_dir(Path(override).expanduser().resolve())
    return _ensure_dir(Path(_DIRS.user_data_path))


def config_dir() -> Path:
    return _ensure_dir(Path(_DIRS.user_config_path))


def log_dir() -> Path:
    return _ensure_dir(Path(_DIRS.user_log_path))


def db_path() -> Path:
    return data_dir() / DB_FILENAME


def ensure_runtime_dirs() -> None:
    data_dir()
    config_dir()
    log_dir()


def migrate_legacy_repo_db() -> bool:
    """Migrate legacy repo-local ./data/am4ops.db to the managed data dir."""
    ensure_runtime_dirs()
    target = db_path()
    if target.exists():
        return False
    legacy = _repo_root() / "data" / DB_FILENAME
    if not legacy.exists():
        return False
    shutil.copy2(legacy, target)
    return True

