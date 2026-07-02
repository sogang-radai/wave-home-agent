from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def utcnow() -> datetime:
    """Naive UTC datetime, safe for SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso_kst(dt: datetime) -> str:
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(KST).isoformat(timespec="seconds")
