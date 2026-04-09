"""Summarize pyinstrument direct HTML: top subtree time + self-time by identifier prefix."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
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


def self_time(node: dict) -> float:
    t = float(node.get("time") or 0)
    kids = node.get("children") or []
    return t - sum(float(c.get("time") or 0) for c in kids)


def walk(
    node: dict,
    acc_self: defaultdict[str, float],
    acc_total: defaultdict[str, float],
    nodes_self: list[tuple[float, str]],
    nodes_total: list[tuple[float, str]],
) -> None:
    ident = str(node.get("identifier") or "?")
    st = self_time(node)
    tot = float(node.get("time") or 0)
    if st > 0:
        acc_self[ident] += st
        nodes_self.append((st, ident))
    if tot > 0:
        acc_total[ident] += tot
        nodes_total.append((tot, ident))
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            walk(ch, acc_self, acc_total, nodes_self, nodes_total)


def main() -> None:
    path = Path(sys.argv[1])
    html = path.read_text(encoding="utf-8", errors="replace")
    data = extract_session_data(html)
    if not data:
        print("no sessionData")
        return
    sess = data.get("session") or {}
    print(
        f"duration_s={sess.get('duration'):.3f} sample_count={sess.get('sample_count')}"
    )
    ft = data.get("frame_tree")
    if not isinstance(ft, dict):
        return
    acc_self: defaultdict[str, float] = defaultdict(float)
    acc_total: defaultdict[str, float] = defaultdict(float)
    nodes_self: list[tuple[float, str]] = []
    nodes_total: list[tuple[float, str]] = []
    walk(ft, acc_self, acc_total, nodes_self, nodes_total)
    nodes_self.sort(key=lambda x: -x[0])
    nodes_total.sort(key=lambda x: -x[0])

    proj = str(Path(__file__).resolve().parent.parent)

    def is_interesting(ident: str) -> bool:
        if ident.startswith("[") and ident.endswith("]"):
            return False
        if "site-packages" in ident and "jinja2" not in ident.lower():
            return False
        return True

    print("\nTop 20 nodes by subtree total time (interesting-ish):")
    shown = 0
    for tot, ident in nodes_total:
        if not is_interesting(ident):
            continue
        print(f"  {tot*1000:8.1f} ms  {ident[:130]}")
        shown += 1
        if shown >= 20:
            break

    print("\nTop 15 nodes by self-time (interesting-ish):")
    shown = 0
    for st, ident in nodes_self:
        if not is_interesting(ident):
            continue
        print(f"  {st*1000:8.1f} ms  {ident[:130]}")
        shown += 1
        if shown >= 15:
            break

    # Aggregate: project code (total time in subtree)
    proj_tot = 0.0
    jinja_tot = 0.0
    sqlite_tot = 0.0
    am4_tot = 0.0
    for ident, st in acc_total.items():
        low = ident.lower()
        if proj in ident.replace("\\", "/"):
            proj_tot += st
        if "jinja2" in low or "templates" in low.replace("\\", "/"):
            jinja_tot += st
        if "sqlite" in low:
            sqlite_tot += st
        if "\\am4\\" in ident.lower() or "/am4/" in ident.lower():
            if "am4-ops" not in low:
                am4_tot += st

    print("\nBucket sums (subtree total time, overlapping):")
    print(f"  project tree: {proj_tot*1000:.1f} ms")
    print(f"  jinja/templates paths: {jinja_tot*1000:.1f} ms")
    print(f"  sqlite: {sqlite_tot*1000:.1f} ms")
    print(f"  am4 package paths: {am4_tot*1000:.1f} ms")


if __name__ == "__main__":
    main()
