#!/usr/bin/env python3
"""Remove VCS lines from a pip-compile lock so `pip install --require-hashes` can run.

Direct git/URL dependencies cannot be hashed; install those separately (e.g. in Docker)
before installing from the stripped lock. See Dockerfile and README.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def strip_vcs_from_lock(text: str) -> str:
    # pip-tools emits a WARNING block before the first unhashed VCS line.
    text = re.sub(
        r"(?ms)^# WARNING: pip install will require the following package to be hashed\.\n"
        r"(?:# [^\n]*\n)*"
        r"^([^\s#][^\n]* @ (?:git\+|https?://)[^\n]+)\n"
        r"(    # via[^\n]*\n)+",
        "",
        text,
        count=1,
    )
    # Any remaining VCS direct requirements (no WARNING prefix).
    while True:
        new = re.sub(
            r"(?m)^[^\s#][^\n]* @ (?:git\+|https?://)[^\n]+\n(    # via[^\n]*\n)+",
            "",
            text,
            count=1,
        )
        if new == text:
            break
        text = new
    return text


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="Path to requirements.lock")
    p.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output path (default: stdout)",
    )
    args = p.parse_args()
    out = strip_vcs_from_lock(args.input.read_text(encoding="utf-8"))
    if args.output:
        args.output.write_text(out, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
