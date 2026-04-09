"""AM4 Ops Center launcher."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "AM4OpsCenter"
_DIRS = PlatformDirs(appname=APP_NAME, appauthor="am4-ops-center")


def _config_dir() -> Path:
    p = Path(_DIRS.user_config_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log_dir() -> Path:
    p = Path(_DIRS.user_log_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pid_file() -> Path:
    return _config_dir() / "launcher.pid"


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _pick_port(port_override: int | None) -> int:
    if port_override is not None:
        return int(port_override)
    for p in range(8765, 8776):
        if _is_port_free(p):
            return p
    raise RuntimeError("No free port found in range 8765-8775")


def _write_pid_file(port: int) -> None:
    payload = {"pid": os.getpid(), "port": int(port)}
    _pid_file().write_text(json.dumps(payload), encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        _pid_file().unlink(missing_ok=True)
    except Exception:
        pass


def _message_box(text: str) -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, "AM4 Ops Center", 0x10)
            return
        except Exception:
            pass
    print(text, file=sys.stderr)


def _wait_for_health(port: int, timeout_s: float = 30.0) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _spawn_uvicorn(port: int, debug: bool, log_file: Path) -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "dashboard.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    creationflags = 0
    if os.name == "nt" and not debug:
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    if debug:
        return subprocess.Popen(cmd, creationflags=creationflags)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = log_file.open("a", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        stdout=fh,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="AM4 Ops Center launcher")
    parser.add_argument("--debug", action="store_true", help="Show console output")
    parser.add_argument("--port", type=int, default=None, help="Override port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    args = parser.parse_args()

    port = _pick_port(args.port)
    _write_pid_file(port)
    proc: subprocess.Popen | None = None
    try:
        proc = _spawn_uvicorn(port=port, debug=bool(args.debug), log_file=_log_dir() / "launcher.log")
        if not _wait_for_health(port):
            _message_box("AM4 Ops Center failed to start within 30 seconds.")
            if proc.poll() is None:
                proc.terminate()
            return 2

        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")

        def _shutdown(*_a) -> None:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
        rc = proc.wait()
        return int(rc)
    finally:
        _remove_pid_file()


if __name__ == "__main__":
    raise SystemExit(main())
