"""Structured logging utilities for the trading engine.

Provides a JSON formatter and helper for emitting structured log events
with consistent event types. Supports both JSON and plain-text formats
controlled via ``STA_LOG_FORMAT`` (json | text) and ``STA_LOG_LEVEL``.

Event types
-----------
- ``signal.received``   — external signal ingested
- ``signal.consensus``  — consensus formed across signals
- ``trade.decision``    — agent decided to trade (or not)
- ``trade.executed``    — order placed / confirmed
- ``bridge.poll``       — TaoshiBridge periodic scan
- ``bridge.signal``     — TaoshiBridge emitted a signal
- ``error``             — generic error envelope
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Merge structured extras if present
        event_type = getattr(record, "event_type", None)
        if event_type:
            payload["event_type"] = event_type

        event_data = getattr(record, "event_data", None)
        if event_data and isinstance(event_data, dict):
            payload["data"] = event_data

        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class StructuredTextFormatter(logging.Formatter):
    """Human-readable formatter that surfaces event_type when present."""

    FMT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.FMT, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        event_type = getattr(record, "event_type", None)
        if event_type:
            record.msg = f"[{event_type}] {record.msg}"
        return super().format(record)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def log_event(
    logger: logging.Logger,
    level: int,
    event_type: str,
    msg: str,
    data: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Emit a structured log event.

    Parameters
    ----------
    logger:
        The logger instance to use.
    level:
        Logging level (e.g. ``logging.INFO``).
    event_type:
        One of the canonical event types listed in the module docstring.
    msg:
        Human-readable message.
    data:
        Optional dict of structured key/value pairs attached to the event.
    """
    extra = {"event_type": event_type}
    if data:
        extra["event_data"] = data
    logger.log(level, msg, extra=extra, **kwargs)


# ---------------------------------------------------------------------------
# Root logger configuration — call once at startup
# ---------------------------------------------------------------------------


def setup_logging(
    level: str = "INFO",
    fmt: str = "json",
) -> None:
    """Configure the root logger for the trading engine.

    Parameters
    ----------
    level:
        Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    fmt:
        ``"json"`` for machine-readable output, ``"text"`` for human-readable.
    """
    root = logging.getLogger()

    # Prevent duplicate handlers on repeated calls (e.g. tests)
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)

    if fmt.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(StructuredTextFormatter())

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)
    handler.setLevel(numeric_level)
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for name in ("urllib3", "httpcore", "httpx", "asyncio", "websockets"):
        logging.getLogger(name).setLevel(logging.WARNING)
