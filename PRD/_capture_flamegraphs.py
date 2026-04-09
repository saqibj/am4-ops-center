"""One-off: warm + fetch pyinstrument HTML for Phase 2 pages; print top self-time frames."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "flamegraphs"

# (slug, path with profile=1 already in query string logic)
PAGES: list[tuple[str, str]] = [
    ("contributions", "/contributions"),
    ("index", "/"),
    ("hub-explorer", "/hub-explorer"),
    ("my-fleet", "/my-fleet"),
    ("buy-next-hub-lax", "/buy-next?hub=LAX"),
    ("my-routes", "/my-routes"),
]


def profile_url(base: str, path: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{base}{path}{sep}profile=1"


def fetch(url: str, timeout: int = 600) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "phase2-flamegraph-capture/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _extract_session_data_json(html: str) -> dict | None:
    """Parse pyinstrument 5 HTML: const sessionData = {...}; pyinstrumentHTMLRenderer.render"""
    marker = "const sessionData = "
    i = html.find(marker)
    if i < 0:
        return None
    i += len(marker)
    if i >= len(html) or html[i] != "{":
        return None
    depth = 0
    start = i
    for j in range(i, len(html)):
        c = html[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                blob = html[start : j + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def _self_time(node: dict) -> float:
    t = float(node.get("time") or 0)
    kids = node.get("children") or []
    return t - sum(float(c.get("time") or 0) for c in kids)


def _walk_frame_tree(
    node: dict | None, ancestors: list[str]
) -> list[tuple[float, str, list[str]]]:
    if not isinstance(node, dict):
        return []
    ident = str(node.get("identifier") or "?")
    st = _self_time(node)
    stack = ancestors + [ident]
    out: list[tuple[float, str, list[str]]] = [(st, ident, stack)]
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            out.extend(_walk_frame_tree(ch, stack))
    return out


def top_self_from_html(html: bytes, n: int = 25) -> list[tuple[float, str, list[str]]]:
    text = html.decode("utf-8", errors="replace")
    data = _extract_session_data_json(text)
    if not data:
        return []
    frame_tree = data.get("frame_tree")
    if not isinstance(frame_tree, dict):
        return []
    rows = _walk_frame_tree(frame_tree, [])
    rows.sort(key=lambda x: -x[0])
    return rows[:n]


def session_duration_ms(html: bytes) -> float | None:
    text = html.decode("utf-8", errors="replace")
    data = _extract_session_data_json(text)
    if not data:
        return None
    sess = data.get("session")
    if isinstance(sess, dict) and "duration" in sess:
        return float(sess["duration"]) * 1000
    return None


def aggregate_identifier_self_time(html: bytes) -> list[tuple[float, str]]:
    """Sum self-time per identifier (helps spot hot functions split across calls)."""
    text = html.decode("utf-8", errors="replace")
    data = _extract_session_data_json(text)
    if not data:
        return []
    ft = data.get("frame_tree")
    if not isinstance(ft, dict):
        return []
    acc: dict[str, float] = {}

    def walk(node: dict) -> None:
        ident = str(node.get("identifier") or "?")
        acc[ident] = acc.get(ident, 0.0) + _self_time(node)
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                walk(ch)

    walk(ft)
    ranked = sorted(acc.items(), key=lambda x: -x[1])
    return ranked[:40]


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8766",
        help="Dashboard base URL (no trailing slash)",
    )
    args = ap.parse_args()
    base = args.base.rstrip("/")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[
        tuple[str, float, float | None, list[tuple[float, str, list[str]]], list[tuple[float, str]]]
    ] = []

    for slug, path in PAGES:
        warm_url = f"{base}{path}"
        purl = profile_url(base, path)
        print(f"\n=== {slug} ===", flush=True)
        print(f"  warm: {warm_url}", flush=True)
        t0 = time.perf_counter()
        try:
            fetch(warm_url)
        except Exception as e:
            print(f"  WARM FAILED: {e}", flush=True)
            continue
        print(f"  warm done in {(time.perf_counter()-t0):.1f}s", flush=True)

        print(f"  profile: {purl}", flush=True)
        t1 = time.perf_counter()
        try:
            status, body = fetch(purl)
        except Exception as e:
            print(f"  PROFILE FAILED: {e}", flush=True)
            continue
        elapsed = time.perf_counter() - t1
        out_path = OUT_DIR / f"{slug}.html"
        out_path.write_bytes(body)
        print(f"  saved {out_path} ({len(body)} bytes, http {status}, {elapsed:.1f}s)", flush=True)

        tops = top_self_from_html(body)
        dur_ms = session_duration_ms(body)
        agg = aggregate_identifier_self_time(body)
        print(
            f"  session.duration (wall): {dur_ms:.1f} ms"
            if dur_ms is not None
            else "  session.duration: unknown",
            flush=True,
        )
        print(f"  top single-node self-time (first 10):", flush=True)
        for row in tops[:10]:
            print(f"    {row[0]*1000:.1f}ms  {row[1][:120]}", flush=True)
        print(f"  top aggregated by identifier (first 8):", flush=True)
        for ident, st in agg[:8]:
            print(f"    {st*1000:.1f}ms total self  {ident[:100]}", flush=True)
        results.append((slug, elapsed, dur_ms, tops, agg))

    # Write a small JSON sidecar for the report
    summary_path = OUT_DIR / "_parsed_top_frames.json"
    serializable = []
    for slug, elapsed, dur_ms, tops, agg in results:
        serializable.append(
            {
                "slug": slug,
                "fetch_seconds": elapsed,
                "session_duration_ms": dur_ms,
                "top_nodes": [
                    {"self_ms": t * 1000, "label": lab, "stack_depth": len(st)}
                    for t, lab, st in tops[:20]
                ],
                "aggregated_identifier_self_ms": [
                    {"identifier": ident, "self_ms": st * 1000} for ident, st in agg[:30]
                ],
            }
        )
    summary_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    print(f"\nWrote {summary_path}", flush=True)


if __name__ == "__main__":
    main()
