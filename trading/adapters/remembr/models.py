from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class TradeResult:
    id: str
    parent_trade_id: Optional[str]
    memory_id: str
    ticker: str
    direction: str
    price: float
    quantity: float
    status: str
    parent_status: Optional[str]
    pnl: Optional[float]
    created_at: datetime


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_entry_price: float
    paper: bool


@dataclass
class TradingStats:
    total_trades: int
    win_count: int
    loss_count: int
    win_rate: Optional[float]
    profit_factor: Optional[float]
    total_pnl: float
    avg_pnl_percent: Optional[float]
    best_trade_pnl: Optional[float]
    worst_trade_pnl: Optional[float]
    sharpe_ratio: Optional[float]
    current_streak: int
    paper: bool


@dataclass
class BulkImportError:
    index: int
    ref: Optional[str]
    reason: str


@dataclass
class BulkImportResult:
    total: int
    succeeded: int
    failed: int
    errors: List[BulkImportError]


@dataclass
class RiskMetrics:
    ticker: str
    paper: bool
    quantity: str
    avg_entry_price: str
    market_price: str
    unrealized_pnl: float
    exposure: float
    exposure_pct: Optional[float] = None


@dataclass
class DrawdownResult:
    max_drawdown: float
    peak: float
    trough: float


@dataclass
class ReplayResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    trades: list


@dataclass
class SignalEntry:
    trade_id: str
    agent_id: str
    agent_name: Optional[str]
    ticker: str
    direction: str
    entry_price: str
    exit_price: Optional[str]
    quantity: str
    pnl: Optional[str]
    status: str
    strategy: Optional[str]
    tags: Optional[list]
    entry_at: Optional[str]
    exit_at: Optional[str]
    created_at: str


@dataclass
class PortfolioPosition:
    ticker: str
    total_quantity: float
    avg_entry_price: float
    agent_count: int


@dataclass
class PortfolioSummary:
    positions: list  # List[PortfolioPosition]
    aggregate_stats: dict
    agents: list
