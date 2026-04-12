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
cur = c.execute(
    """
    UPDATE my_hubs
    SET last_extract_status = NULL,
        last_extract_error = NULL
    WHERE last_extract_status = 'error'
"""
)
c.commit()
print("Cleared error state on", cur.rowcount, "hubs")
c.close()
