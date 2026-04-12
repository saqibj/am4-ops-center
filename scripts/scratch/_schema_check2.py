from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.env_compat import effective_db_path  # noqa: E402
from app.paths import db_path  # noqa: E402

DB = effective_db_path(str(db_path()))
print("size:", os.path.getsize(DB))
c = sqlite3.connect(DB)
rows = list(c.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
print("tables:", len(rows))
for name, sql in rows:
    print("---", name)
    print(sql)
# specifically my_hubs
print("=== my_hubs indexes ===")
for r in c.execute("SELECT sql FROM sqlite_master WHERE tbl_name='my_hubs'"):
    print(r[0])
