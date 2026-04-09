"""
Profile dashboard pages with pyinstrument by forcing Starlette to run sync routes
on the main thread (monkeypatch run_in_threadpool). This matches HTTP behavior but
makes pyinstrument see Jinja/sqlite work — the stock middleware only samples the
asyncio thread and misses thread-pool work.

Measurement-only script; not used in production.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# DB before any dashboard import
os.environ.setdefault("AM4_ROUTEMINE_DB", str(_ROOT / "am4_data.db"))


async def _run_inline(func, *args, **kwargs):
    return func(*args, **kwargs)


def main() -> None:
    import starlette.concurrency as sc

    sc.run_in_threadpool = _run_inline  # type: ignore[assignment]

    from pyinstrument import Profiler
    from fastapi.testclient import TestClient

    from dashboard.server import app

    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="e.g. /contributions or /buy-next?hub=LAX")
    ap.add_argument("-o", "--output", required=True, help="output .html path")
    args = ap.parse_args()

    client = TestClient(app)
    path = args.path
    if not path.startswith("/"):
        path = "/" + path

    profiler = Profiler(async_mode="enabled")
    profiler.start()
    try:
        r = client.get(path)
    finally:
        profiler.stop()

    Path(args.output).write_text(profiler.output_html(), encoding="utf-8")
    print(f"status={r.status_code} len={len(r.content)} wrote {args.output}")


if __name__ == "__main__":
    main()
