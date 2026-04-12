from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.env_compat import effective_db_path  # noqa: E402
from app.paths import db_path  # noqa: E402

DB = effective_db_path(str(db_path()))
c = sqlite3.connect(DB)
c.execute("PRAGMA foreign_keys = OFF")
t0 = time.time()
print("Before:", c.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0])
c.execute(
    """
    DELETE FROM route_aircraft
    WHERE id NOT IN (
        SELECT MAX(id) FROM route_aircraft
        GROUP BY origin_id, dest_id, aircraft_id
    )
"""
)
c.commit()
print("After:", c.execute("SELECT COUNT(*) FROM route_aircraft").fetchone()[0])
print(f"Elapsed: {time.time() - t0:.1f}s")
