#!/usr/bin/env python3
"""Verify AIRCRAFT_MAP shortnames resolve in am4. Run from repo root."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
for p in (SCRIPTS_DIR, ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from convert_csv import AIRCRAFT_MAP  # noqa: E402


def main() -> int:
    try:
        from am4.utils.aircraft import Aircraft
        from am4.utils.db import init
    except ImportError as e:
        print(f"SKIP: am4 not importable ({e})")
        return 0

    init()
    failed: list[tuple[str, str, str]] = []
    for csv_name, shortname in sorted(AIRCRAFT_MAP.items()):
        try:
            result = Aircraft.search(shortname)
            if not result.ac.valid:
                failed.append((csv_name, shortname, "not valid"))
            else:
                print(f"OK  {csv_name:35s} -> {shortname:10s} ({result.ac.name})")
        except Exception as exc:  # noqa: BLE001
            failed.append((csv_name, shortname, str(exc)))

    if failed:
        print("\nFAILED:")
        for csv_name, shortname, err in failed:
            print(f"  {csv_name:35s} -> {shortname:10s}: {err}")
        return 1
    print(f"\n{len(AIRCRAFT_MAP)} mappings verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
