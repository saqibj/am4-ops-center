#!/usr/bin/env bash
# Regenerate pinned requirements from requirements.in (Python 3.12 recommended to match Docker).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -q pip-tools
python3 -m piptools compile --output-file=requirements.txt requirements.in
python3 -m piptools compile --generate-hashes --output-file=requirements.lock requirements.in
