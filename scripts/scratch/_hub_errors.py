from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.env_compat import effective_db_path  # noqa: E402
from app.paths import db_path  # noqa: E402

DB = effective_db_path(str(db_path()))
c = sqlite3.connect(DB)
for r in c.execute(
    """
    SELECT a.iata, mh.last_extract_status, mh.last_extract_error, mh.last_extracted_at
    FROM my_hubs mh JOIN airports a ON mh.airport_id = a.id
    WHERE mh.last_extract_status = 'error'
"""
):
    print(r[0], "|", r[1], "|", r[3])
    print("  error:", r[2])
    print()
