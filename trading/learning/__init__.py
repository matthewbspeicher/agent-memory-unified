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
    from learning.ensemble_optimizer import (
        AgentWeight,
        EnsembleConfig,
        EnsembleMethod,
        EnsembleOptimizer,
        EnsembleSignal,
    )
    from learning.forecast import (
        DirectionalForecastModel,
        ForecastOutput,
        TimeSeriesForecaster,
    )
    from learning.rl_position_sizer import (
        RLPositionSizer,
        SizingState,
        TradingSizingEnv,
    )


# Lazy import mapping - import only when accessed
_LAZY_IMPORTS = {
    "CorrelationConfig": "learning.correlation_monitor",
    "CorrelationMonitor": "learning.correlation_monitor",
    "CorrelationPair": "learning.correlation_monitor",
    "CorrelationSnapshot": "learning.correlation_monitor",
    "AgentWeight": "learning.ensemble_optimizer",
    "EnsembleConfig": "learning.ensemble_optimizer",
    "EnsembleMethod": "learning.ensemble_optimizer",
    "EnsembleOptimizer": "learning.ensemble_optimizer",
    "EnsembleSignal": "learning.ensemble_optimizer",
    "DirectionalForecastModel": "learning.forecast",
    "ForecastOutput": "learning.forecast",
    "TimeSeriesForecaster": "learning.forecast",
    "RLPositionSizer": "learning.rl_position_sizer",
    "SizingState": "learning.rl_position_sizer",
    "TradingSizingEnv": "learning.rl_position_sizer",
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module 'learning' has no attribute {name!r}")
