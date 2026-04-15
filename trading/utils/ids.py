"""ID generation utilities."""

from __future__ import annotations

import ulid


def new_signal_id() -> str:
    """Return a fresh ULID as a 26-char Crockford base32 string.

    ULIDs are lexicographically sortable by creation time and crash-safe to
    generate without coordination — suitable as opaque public signal_ids.
    """
    return str(ulid.new())
