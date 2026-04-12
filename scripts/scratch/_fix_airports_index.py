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
    c.execute("DROP INDEX IF EXISTS idx_airports_iata_unique")
    c.execute("CREATE UNIQUE INDEX idx_airports_iata_unique ON airports(iata)")
    c.commit()
    print("Migration OK")
    # Verify
    for r in c.execute("SELECT sql FROM sqlite_master WHERE name='idx_airports_iata_unique'"):
        print("New index:", r[0])
except Exception as e:
    print("FAIL:", type(e).__name__, e)
finally:
    c.close()
