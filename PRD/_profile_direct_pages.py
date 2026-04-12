"""
Call page_* handlers directly in-process so pyinstrument samples real Python work
(Jinja, sqlite via get_db, etc.). Starlette sync routes + TestClient run the app
on another thread, which pyinstrument misses.

Measurement-only; not production code.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.env_compat import ensure_default_db_env  # noqa: E402
from app.paths import db_path  # noqa: E402

ensure_default_db_env(str(db_path()))

from starlette.requests import Request

# Load app first so dashboard.routes.* resolves without partial-init cycles.
import dashboard.server  # noqa: F401

from dashboard.routes import pages as pages_mod


def make_request(path_with_query: str) -> Request:
    path_only, _, qs = path_with_query.partition("?")
    if not path_only.startswith("/"):
        path_only = "/" + path_only
    scope: dict = {
        "type": "http",
        "asgi": {"spec_version": "2.4", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path_only,
        "raw_path": path_only.encode("utf-8"),
        "query_string": qs.encode("utf-8") if qs else b"",
        "headers": [(b"host", b"127.0.0.1")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8766),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


PAGES: list[tuple[str, str, str]] = [
    ("contributions", "/contributions", "page_contributions"),
    ("index", "/", "page_index"),
    ("hub-explorer", "/hub-explorer", "page_hub_explorer"),
    ("my-fleet", "/my-fleet", "page_my_fleet"),
    ("buy-next-hub-lax", "/buy-next?hub=LAX", "page_buy_next"),
    ("my-routes", "/my-routes", "page_my_routes"),
]


def main() -> None:
    from pyinstrument import Profiler

    out_dir = _ROOT / "PRD" / "flamegraphs"
    out_dir.mkdir(parents=True, exist_ok=True)

    for slug, path, fn_name in PAGES:
        fn = getattr(pages_mod, fn_name)
        req = make_request(path)
        print(f"\n=== warm {slug} ===", flush=True)
        fn(req)
        print(f"=== profile {slug} ===", flush=True)
        req2 = make_request(path)
        profiler = Profiler(async_mode="enabled")
        profiler.start()
        try:
            fn(req2)
        finally:
            profiler.stop()
        outp = out_dir / f"{slug}-direct.html"
        outp.write_text(profiler.output_html(), encoding="utf-8")
        print(f"wrote {outp}", flush=True)


if __name__ == "__main__":
    main()
