from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.paths import db_path  # noqa: E402

DB = os.environ.get("AM4_ROUTEMINE_DB", str(db_path()))
c = sqlite3.connect(DB)
# Check for rows that would violate a plain unique constraint
dupes = list(
    c.execute(
        """
    SELECT iata, COUNT(*) FROM airports
    WHERE iata IS NULL OR TRIM(iata) = ''
    GROUP BY iata HAVING COUNT(*) > 1
"""
    )
)
print("NULL/empty iata dupes:", dupes)
print(
    "NULL count:",
    c.execute(
        "SELECT COUNT(*) FROM airports WHERE iata IS NULL OR TRIM(iata)=''"
    ).fetchone()[0],
)
