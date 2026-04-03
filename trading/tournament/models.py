from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StageThreshold:
    min_sharpe: float
    min_trades: int
    max_drawdown: float
    min_win_rate: float


@dataclass
class LiveLimitedConfig:
    max_capital_pct: float
    max_capital_usd: float


@dataclass
class AuditRow:
    id: int | None
    agent_name: str
    from_stage: int
    to_stage: int
    reason: str
    ai_analysis: str
    ai_recommendation: str
    timestamp: str
    overridden_by: str | None
