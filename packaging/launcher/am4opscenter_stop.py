"""Stop AM4 Ops Center launcher-managed process."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "AM4OpsCenter"
_DIRS = PlatformDirs(appname=APP_NAME, appauthor="am4-ops-center")


def _pid_file() -> Path:
    p = Path(_DIRS.user_config_path)
    p.mkdir(parents=True, exist_ok=True)
    return p / "launcher.pid"


def _read_pid() -> int | None:
    path = _pid_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("pid"))
    except Exception:
        return None


def _remove_pid() -> None:
    try:
        _pid_file().unlink(missing_ok=True)
    except Exception:
        pass


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> int:
    pid = _read_pid()
    if pid is None:
        print("Not running")
        return 0

    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], check=False, capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            _remove_pid()
            print("Not running")
            return 0

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _is_running(pid):
            _remove_pid()
            print("Stopped")
            return 0
        time.sleep(0.2)

    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    _remove_pid()
    print("Stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

