"""Dump all frame_tree nodes with time > threshold from pyinstrument HTML."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def extract_session_data(html: str) -> dict | None:
    marker = "const sessionData = "
    i = html.find(marker)
    if i < 0:
        return None
    i += len(marker)
    depth = 0
    for j in range(i, len(html)):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[i : j + 1])
    return None


def walk(node: dict, depth: int = 0) -> list[tuple[float, str]]:
    t = float(node.get("time") or 0)
    ident = str(node.get("identifier") or "?")
    rows = [(t, ident)]
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            rows.extend(walk(ch, depth + 1))
    return rows


def main() -> None:
    path = Path(sys.argv[1])
    html = path.read_text(encoding="utf-8", errors="replace")
    data = extract_session_data(html)
    if not data:
        print("no sessionData")
        return
    ft = data.get("frame_tree")
    sess = data.get("session") or {}
    print("duration_s", sess.get("duration"), "sample_count", sess.get("sample_count"))
    if not isinstance(ft, dict):
        print("no frame_tree")
        return
    rows = walk(ft)
    rows.sort(key=lambda x: -x[0])
    print("\nTop 40 by total time in subtree:")
    for t, ident in rows[:40]:
        if t < 0.001:
            continue
        print(f"  {t*1000:10.1f} ms  {ident[:140]}")


if __name__ == "__main__":
    main()
