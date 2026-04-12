from __future__ import annotations

import os
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
print("Before:", os.path.getsize(DB) / 1e9, "GB")
c = sqlite3.connect(DB)
t0 = time.time()
c.execute("VACUUM")
c.close()
print("After:", os.path.getsize(DB) / 1e9, "GB")
print(f"Elapsed: {time.time() - t0:.1f}s")
