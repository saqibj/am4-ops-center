"""Local encrypted credentials storage for setup wizard."""

from __future__ import annotations

import base64
import hashlib
import json
import platform
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from app.paths import config_dir


def _credentials_path() -> Path:
    return config_dir() / "credentials.json"


def _machine_key_material() -> bytes:
    ident = f"{platform.system()}|{platform.node()}|{uuid.getnode()}"
    return ident.encode("utf-8")


def _fernet() -> Fernet:
    digest = hashlib.sha256(_machine_key_material()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def store_credentials(payload: dict[str, str]) -> None:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    token = _fernet().encrypt(raw).decode("utf-8")
    path = _credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"encrypted": token}, ensure_ascii=True), encoding="utf-8")


def load_credentials() -> dict[str, str] | None:
    path = _credentials_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    token = str(data.get("encrypted", "")).strip()
    if not token:
        return None
    raw = _fernet().decrypt(token.encode("utf-8"))
    parsed = json.loads(raw.decode("utf-8"))
    return {str(k): str(v) for k, v in parsed.items()}

