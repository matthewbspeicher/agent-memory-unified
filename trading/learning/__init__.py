"""Learning modules for strategy analysis and optimization.

Lazy imports to avoid eager loading of optional dependencies (gymnasium, torch, etc.).
Modules are only imported when explicitly accessed via attribute access.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from learning.correlation_monitor import (
        CorrelationConfig,
        CorrelationMonitor,
        CorrelationPair,
        CorrelationSnapshot,
    )


# Lazy import mapping - import only when accessed
_LAZY_IMPORTS = {
    "CorrelationConfig": "learning.correlation_monitor",
    "CorrelationMonitor": "learning.correlation_monitor",
    "CorrelationPair": "learning.correlation_monitor",
    "CorrelationSnapshot": "learning.correlation_monitor",
}

__all__ = [
    "CorrelationConfig",
    "CorrelationMonitor",
    "CorrelationPair",
    "CorrelationSnapshot",
]


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module 'learning' has no attribute {name!r}")
