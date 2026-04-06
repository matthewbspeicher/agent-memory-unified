from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StrategySummary:
    """One row in the ranked scorecard."""

    agent_name: str
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    flat_count: int = 0
    win_rate: float = 0.0
    gross_pnl: str = "0"
    net_pnl: str = "0"
    avg_gross_pnl: str = "0"
    avg_net_pnl: str = "0"
    avg_win: str = "0"
    avg_loss: str = "0"
    expectancy: str = "0"  # win_rate * avg_win + loss_rate * avg_loss
    profit_factor: float | None = (
        None  # sum(wins) / abs(sum(losses)); None if no losses, 0.0 if no wins
    )
    avg_hold_minutes: float = 0.0
    median_hold_minutes: float = 0.0
    best_trade: str = "0"
    worst_trade: str = "0"
    max_drawdown: str = "0"  # peak-to-trough in dollars on cumulative net PnL curve


@dataclass
class RollingPoint:
    """One point on a rolling time series."""

    exit_time: str
    cumulative_net_pnl: str = "0"
    rolling_expectancy: str | None = None


@dataclass
class SymbolBreakdown:
    """Performance by symbol for a single strategy."""

    symbol: str
    trade_count: int = 0
    win_rate: float = 0.0
    net_pnl: str = "0"
    avg_net_pnl: str = "0"
    expectancy: str = "0"


@dataclass
class ExitReasonBreakdown:
    """Performance by exit reason for a single strategy."""

    exit_reason: str
    trade_count: int = 0
    win_rate: float = 0.0
    net_pnl: str = "0"


@dataclass
class StrategyDrilldown:
    """Full drilldown for one strategy."""

    summary: StrategySummary
    equity_curve: list[RollingPoint] = field(default_factory=list)
    rolling_expectancy_20: list[RollingPoint] = field(default_factory=list)
    rolling_expectancy_50: list[RollingPoint] = field(default_factory=list)
    top_symbols: list[SymbolBreakdown] = field(default_factory=list)
    bottom_symbols: list[SymbolBreakdown] = field(default_factory=list)
    exit_reasons: list[ExitReasonBreakdown] = field(default_factory=list)
