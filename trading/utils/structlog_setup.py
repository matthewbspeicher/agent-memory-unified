"""Structlog configuration for structured logging with correlation IDs.

Replaces the custom JSONFormatter with structlog for automatic:
- Trace ID injection (via asgi-correlation-id)
- Structured key-value logging
- Multiple output formats (JSON/console)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_structlog(
    level: str = "INFO",
    format: str = "json",
) -> None:
    """Configure structlog for the trading engine.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format: Output format ("json" or "console")
    """

    # Determine processors based on format
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if format == "console":
        # Human-readable console output
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # JSON output for log aggregation
        processors.append(structlog.processors.JSONRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # Ensure all loggers use our configuration
    for name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog-bound logger."""
    return structlog.get_logger(name)


# Convenience: configure on import based on env vars
import os

_format = os.getenv("STA_LOG_FORMAT", "json")
_level = os.getenv("STA_LOG_LEVEL", "INFO")
configure_structlog(level=_level, format=_format)
