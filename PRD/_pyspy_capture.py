"""Attach py-spy to the uvicorn PID while issuing one warm HTTP request (sync route work)."""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:8766"

PAGES: list[tuple[str, str]] = [
    ("contributions", "/contributions"),
    ("index", "/"),
    ("hub-explorer", "/hub-explorer"),
    ("my-fleet", "/my-fleet"),
    ("buy-next-hub-lax", "/buy-next?hub=LAX"),
    ("my-routes", "/my-routes"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--out-dir", default="PRD/flamegraphs")
    ap.add_argument("--duration", type=float, default=45.0)
    ap.add_argument("--rate", type=int, default=200)
    args = ap.parse_args()

    import os
    from pathlib import Path

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for slug, path in PAGES:
        url = f"{BASE}{path}"
        out_svg = out_dir / f"{slug}-pyspy.svg"
        warm_url = url
        print(f"\n=== {slug} ===", flush=True)
        print(f"  warm: {warm_url}", flush=True)
        try:
            urllib.request.urlopen(warm_url, timeout=600)
        except Exception as e:
            print(f"  warm failed: {e}", flush=True)
            continue

        print(f"  py-spy -> {out_svg}", flush=True)
        cmd = [
            "py-spy",
            "record",
            "-o",
            str(out_svg),
            "-p",
            str(args.pid),
            "--duration",
            str(int(args.duration)),
            "--rate",
            str(args.rate),
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def fire():
            time.sleep(0.3)
            print(f"  GET {url}", flush=True)
            try:
                urllib.request.urlopen(url, timeout=600)
            except Exception as e:
                print(f"  request error: {e}", flush=True)

        threading.Thread(target=fire, daemon=True).start()
        out, err = proc.communicate()
        if proc.returncode != 0:
            print(err.decode("utf-8", errors="replace"), file=sys.stderr)
        print(f"  py-spy exit {proc.returncode}", flush=True)


if __name__ == "__main__":
    main()
