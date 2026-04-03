from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CommissionModel(str, Enum):
    ZERO = "zero"
    FLAT_PER_SHARE = "flat_per_share"
    FLAT_PER_CONTRACT = "flat_per_contract"
    PERCENT_OF_NOTIONAL = "percent_of_notional"
    FIDELITY = "fidelity"
    IBKR = "ibkr"


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""

    name: str
    agent_names: list[str]  # agents to backtest
    symbols: list[str]  # tickers to trade
    start_date: date | str
    end_date: date | str
    timeframe: str = "1d"  # bar timeframe
    initial_capital: Decimal = Decimal("100000")
    commission: CommissionModel = CommissionModel.ZERO
    commission_params: dict[str, Any] = field(default_factory=dict)
    slippage_bps: float = 0.0  # simulated slippage in bps
    allow_short: bool = False
    margin_pct: Decimal = Decimal("50")  # margin requirement %
    risk_free_rate: float = 0.05  # for Sharpe calculation
    replay_speed: float = 0.0  # 0 = instant, >0 = seconds per bar
    warmup_bars: int = 100  # bars before trading begins
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeRecord:
    """A single simulated trade during backtesting."""

    id: str
    agent_name: str
    symbol: str
    side: str  # "BUY" | "SELL"
    entry_time: datetime
    entry_price: Decimal
    quantity: Decimal
    exit_time: datetime | None = None
    exit_price: Decimal | None = None
    pnl: Decimal = Decimal("0")
    pnl_pct: float = 0.0
    commission: Decimal = Decimal("0")
    holding_bars: int = 0
    signal: str = ""
    reasoning: str = ""

    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": str(self.entry_price),
            "quantity": str(self.quantity),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": str(self.exit_price) if self.exit_price else None,
            "pnl": str(self.pnl),
            "pnl_pct": self.pnl_pct,
            "commission": str(self.commission),
            "holding_bars": self.holding_bars,
            "signal": self.signal,
            "reasoning": self.reasoning,
        }


@dataclass
class EquityPoint:
    """A point on the equity curve."""

    timestamp: datetime
    equity: Decimal
    cash: Decimal
    positions_value: Decimal
    agent_name: str | None = None  # None = portfolio-level


@dataclass
class BacktestResult:
    """Complete results of a backtest run."""

    config: BacktestConfig
    status: BacktestStatus
    started_at: datetime
    completed_at: datetime | None = None
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)

    # Summary metrics
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade_pnl: Decimal = Decimal("0")
    avg_winning_trade: Decimal = Decimal("0")
    avg_losing_trade: Decimal = Decimal("0")
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    avg_holding_bars: float = 0.0
    total_commission: Decimal = Decimal("0")
    final_equity: Decimal = Decimal("0")
    final_cash: Decimal = Decimal("0")

    # Per-agent breakdown
    agent_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)

    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.config.name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "avg_trade_pnl": str(self.avg_trade_pnl),
            "avg_winning_trade": str(self.avg_winning_trade),
            "avg_losing_trade": str(self.avg_losing_trade),
            "largest_win": str(self.largest_win),
            "largest_loss": str(self.largest_loss),
            "avg_holding_bars": self.avg_holding_bars,
            "total_commission": str(self.total_commission),
            "final_equity": str(self.final_equity),
            "final_cash": str(self.final_cash),
            "agent_metrics": self.agent_metrics,
            "trade_count": len(self.trades),
            "error": self.error,
        }
