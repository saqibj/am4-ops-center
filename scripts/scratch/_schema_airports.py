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
for r in c.execute(
    "SELECT sql FROM sqlite_master WHERE tbl_name='airports' AND sql IS NOT NULL"
):
    print(r[0])
    print("---")
