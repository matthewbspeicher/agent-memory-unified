"""Shared JSON encoding/decoding for storage modules."""

from __future__ import annotations

from copy import copy
import json
from typing import Any


def encode_json(value: Any) -> str | None:
    """Encode a value to JSON string, or None if input is None."""
    if value is None:
        return None
    return json.dumps(value)


def decode_json_column(value: Any) -> Any:
    """Decode a single JSON column value.

    Handles: None, already-parsed dicts/lists, and JSON strings.
    Works with both SQLite (strings) and asyncpg (native JSONB).
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def decode_json_columns(
    row: dict[str, Any],
    columns: list[str],
    fallback: Any = None,
) -> dict[str, Any]:
    """Decode multiple JSON columns in a row dict, mutating in-place.

    If a column fails to parse and fallback is provided, uses fallback.
    """
    for col in columns:
        val = row.get(col)
        if isinstance(val, str):
            try:
                row[col] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                if fallback is not None:
                    row[col] = copy(fallback)
        elif val is None and fallback is not None:
            row[col] = copy(fallback)
    return row
