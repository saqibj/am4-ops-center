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


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _install_root() -> Path:
    return Path(sys.executable).resolve().parent


def _bundled_venv_python() -> Path | None:
    """Python from the installer's venv (Windows: runtime\\Scripts\\python.exe)."""
    root = _install_root()
    if os.name == "nt":
        cand = root / "runtime" / "Scripts" / "python.exe"
    else:
        cand = root / "runtime" / "bin" / "python3"
        if not cand.is_file():
            cand = root / "runtime" / "bin" / "python"
    return cand if cand.is_file() else None


def _dev_source_root() -> Path | None:
    """Repo root (directory that contains ``dashboard``) when running from source."""
    here = Path(__file__).resolve().parent
    for base in (here, *here.parents):
        if (base / "dashboard").is_dir():
            return base
    return None


def _python_for_uvicorn(debug: bool) -> Path | None:
    if _is_frozen():
        v = _bundled_venv_python()
        if v is None:
            _message_box(
                "The bundled Python environment is missing (expected "
                "runtime\\Scripts\\python.exe next to this program). "
                "Reinstall AM4 Ops Center."
            )
            return None
        return v
    if debug:
        import shutil

        w = shutil.which("python")
        if w:
            return Path(w)
    return Path(sys.executable)


def _uvicorn_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    if _is_frozen():
        app_src = _install_root() / "app"
        if app_src.is_dir():
            extra = str(app_src)
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = extra + (os.pathsep + prev if prev else "")
    else:
        root = _dev_source_root()
        if root is not None:
            extra = str(root)
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = extra + (os.pathsep + prev if prev else "")
    return env


def _uvicorn_cwd() -> Path | None:
    if _is_frozen():
        return _install_root()
    return _dev_source_root()


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


def _spawn_uvicorn(port: int, debug: bool, log_file: Path) -> subprocess.Popen | None:
    py = _python_for_uvicorn(debug)
    if py is None:
        return None
    cmd = [
        str(py),
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

    env = _uvicorn_subprocess_env()
    cwd = _uvicorn_cwd()
    popen_kw: dict = {
        "env": env,
        "creationflags": creationflags,
    }
    if cwd is not None:
        popen_kw["cwd"] = str(cwd)

    if debug:
        return subprocess.Popen(cmd, **popen_kw)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = log_file.open("a", encoding="utf-8")
    popen_kw["stdout"] = fh
    popen_kw["stderr"] = subprocess.STDOUT
    return subprocess.Popen(cmd, **popen_kw)


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
        if proc is None:
            return 1
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
