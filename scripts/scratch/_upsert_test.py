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
try:
    c.execute(
        "INSERT INTO my_hubs (airport_id, notes, is_active, updated_at) VALUES (-9999, 'test', 1, datetime('now')) ON CONFLICT(airport_id) DO UPDATE SET notes='test2'"
    )
    print("UPSERT OK")
    c.execute("DELETE FROM my_hubs WHERE airport_id = -9999")
    c.commit()
except Exception as e:
    print("FAIL:", type(e).__name__, e)
