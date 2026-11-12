"""Reading stored dates and times the same way on both backends.

SQLite returns the ISO text a store wrote. PostgreSQL returns a datetime for a
TIMESTAMP or TIMESTAMPTZ column, naive for TIMESTAMP, which holds UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone


def stored_datetime(value) -> datetime:
    """A stored value as a datetime, parsed from text exactly as before.

    A naive datetime from PostgreSQL is UTC and is returned aware, matching
    the aware ISO text stores write.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value)


def stored_utc(value) -> datetime:
    """A stored value as an aware UTC datetime, for comparing and subtracting."""
    stamp = stored_datetime(value)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
