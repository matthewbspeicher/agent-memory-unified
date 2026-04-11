"""Lightweight data models for trade memory and reflection input."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class TradeMemory:
    symbol: str
    direction: str  # "long" | "short" | "yes" | "no"
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal
    slippage_bps: int
    signal_strength: float  # 0.0–1.0 from Opportunity
    outcome: str  # "win" | "loss" | "scratch"
    hold_duration_mins: int
    timestamp: datetime
    data: dict = field(default_factory=dict)


@dataclass
class ClosedTrade:
    """Enriched trade record passed to TradeReflector after position close."""

    agent_name: str
    opportunity_id: str
    trade_memory: TradeMemory
    expected_pnl: Decimal  # from sizing engine estimate
    stop_loss: Decimal  # stop distance used (negative = dollar loss limit)
