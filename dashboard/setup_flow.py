"""Background extraction flow for first-run setup wizard."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from config import UserConfig
from database.schema import get_connection
from extractors.routes import refresh_single_hub

_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="setup-extract")


@dataclass
class SetupProgress:
    running: bool
    done: bool
    failed: bool
    message: str
    current_hub: str | None
    completed_hubs: int
    total_hubs: int
    rows_inserted: int
    success_hubs: int


_STATE = SetupProgress(
    running=False,
    done=False,
    failed=False,
    message="Not started",
    current_hub=None,
    completed_hubs=0,
    total_hubs=0,
    rows_inserted=0,
    success_hubs=0,
)


def _count_rows_for_hub(db_path: str, hub: str) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM route_aircraft ra
            JOIN airports a ON ra.origin_id = a.id
            WHERE ra.is_valid = 1
              AND UPPER(TRIM(a.iata)) = UPPER(TRIM(?))
            """,
            (hub,),
        ).fetchone()
        return int(row["n"] if row else 0)
    finally:
        conn.close()


def _set_state(**kwargs) -> None:
    with _LOCK:
        for k, v in kwargs.items():
            setattr(_STATE, k, v)


def get_progress() -> SetupProgress:
    with _LOCK:
        return SetupProgress(**_STATE.__dict__)


def start_extraction(db_path: str, hubs: list[str], cfg: UserConfig) -> tuple[bool, str]:
    cur = get_progress()
    if cur.running:
        return False, "Extraction is already running."
    cleaned = [h.strip().upper() for h in hubs if h and h.strip()]
    if not cleaned:
        return False, "Select at least one hub."

    _set_state(
        running=True,
        done=False,
        failed=False,
        message="Starting extraction...",
        current_hub=None,
        completed_hubs=0,
        total_hubs=len(cleaned),
        rows_inserted=0,
        success_hubs=0,
    )

    def _worker() -> None:
        try:
            from am4.utils.db import init

            init()
            total_rows = 0
            success_hubs = 0
            completed = 0
            for hub in cleaned:
                _set_state(current_hub=hub, message=f"Extracting {hub}...")
                try:
                    refresh_single_hub(db_path, cfg, hub)
                    rows = _count_rows_for_hub(db_path, hub)
                    total_rows += rows
                    success_hubs += 1
                finally:
                    completed += 1
                    _set_state(
                        completed_hubs=completed,
                        rows_inserted=total_rows,
                        success_hubs=success_hubs,
                    )
            _set_state(
                running=False,
                done=True,
                failed=False,
                current_hub=None,
                message="Extraction complete.",
                rows_inserted=total_rows,
                success_hubs=success_hubs,
            )
        except Exception as exc:
            _set_state(
                running=False,
                done=True,
                failed=True,
                current_hub=None,
                message=f"Extraction failed: {exc}",
            )

    _EXECUTOR.submit(_worker)
    return True, "Extraction started."

