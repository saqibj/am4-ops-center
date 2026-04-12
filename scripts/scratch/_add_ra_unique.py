from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.paths import db_path  # noqa: E402

DB = os.environ.get("AM4_ROUTEMINE_DB", str(db_path()))
c = sqlite3.connect(DB)
t0 = time.time()
c.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_route_aircraft_triple ON route_aircraft(origin_id, dest_id, aircraft_id)"
)
c.commit()
print(f"Index created in {time.time() - t0:.1f}s")
for r in c.execute("SELECT sql FROM sqlite_master WHERE name='ux_route_aircraft_triple'"):
    print(r[0])
c.close()
