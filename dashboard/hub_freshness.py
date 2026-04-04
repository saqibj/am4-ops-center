"""Hub extract freshness: display status and stale threshold (matches Hub Manager SQL)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

STALE_AFTER_DAYS = 7


def _parse_sqlite_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip()
    if not t:
        return None
    head = t.split(".", 1)[0]
    if len(head) >= 19:
        try:
            return datetime.strptime(head[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if len(head) >= 10:
        try:
            return datetime.strptime(head[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def hub_is_stale_ok(
    last_extracted_at: str | None,
    *,
    now: datetime | None = None,
    stale_days: int = STALE_AFTER_DAYS,
) -> bool:
    """True if last_extracted_at is parseable and older than ``stale_days`` (UTC)."""
    at = _parse_sqlite_ts(last_extracted_at)
    if at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - at) > timedelta(days=stale_days)


def hub_display_status(
    last_extract_status: str | None,
    last_extracted_at: str | None,
    *,
    now: datetime | None = None,
    stale_days: int = STALE_AFTER_DAYS,
) -> str:
    """
    UI status: never | running | ok | error | stale.

    *stale* is derived: ``ok`` in DB but ``last_extracted_at`` older than ``stale_days``.
    """
    st = (last_extract_status or "").strip().lower()
    if st == "running":
        return "running"
    if st == "error":
        return "error"
    if st == "ok":
        if hub_is_stale_ok(last_extracted_at, now=now, stale_days=stale_days):
            return "stale"
        return "ok"
    return "never"
