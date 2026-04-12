"""CLI backup subcommand (SEC-15)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from database.schema import create_schema, get_connection
from main import cmd_backup


def test_backup_writes_readable_copy(tmp_path: Path) -> None:
    src = tmp_path / "am4ops.db"
    conn = get_connection(src)
    create_schema(conn)
    conn.execute("INSERT INTO aircraft (id, shortname, name, type) VALUES (1, 'b738', 'B737-800', 'PAX')")
    conn.commit()
    conn.close()

    out_dir = tmp_path / "backups"
    cmd_backup(SimpleNamespace(db=str(src), output=str(out_dir)))

    files = list(out_dir.glob("am4ops_*.db"))
    assert len(files) == 1
    bak = files[0]
    bconn = sqlite3.connect(str(bak))
    try:
        row = bconn.execute(
            "SELECT shortname FROM aircraft WHERE id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "b738"
    finally:
        bconn.close()
