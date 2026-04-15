"""Job tracking for background hub refresh operations."""

from __future__ import annotations

import sqlite3


def ensure_refresh_jobs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hub_iata TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            progress_pct INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_jobs_hub_status
        ON refresh_jobs(hub_iata, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_jobs_completed_at
        ON refresh_jobs(completed_at)
        """
    )


def mark_orphaned_refresh_jobs_failed(
    conn: sqlite3.Connection, reason: str = "Marked failed at startup after restart."
) -> int:
    ensure_refresh_jobs_schema(conn)
    cur = conn.execute(
        """
        UPDATE refresh_jobs
        SET status = 'failed',
            completed_at = datetime('now'),
            error_message = COALESCE(NULLIF(error_message, ''), ?)
        WHERE status = 'running'
        """,
        (reason,),
    )
    return int(cur.rowcount or 0)
