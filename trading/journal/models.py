from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Optional
from decimal import Decimal

class TradeDecision(BaseModel):
    """
    Captures the semantic context and reasoning behind a trade decision.
    """
    agent_name: str
    symbol: str
    direction: str # e.g. 'BUY', 'SELL', 'LONG', 'SHORT'
    confidence: float
    reasoning: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TradeExecution(BaseModel):
    """
    Captures the actual execution details of a trade.
    """
    order_id: str
    account_id: str
    filled_quantity: Decimal
    avg_fill_price: Decimal
    commission: Decimal = Decimal("0")
    execution_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TradeLifecycle(BaseModel):
    """
    Combines the decision, execution, and exit (if applicable) into a complete journal entry.
    """
    trade_id: str
    decision: TradeDecision
    execution: Optional[TradeExecution] = None
    exit_execution: Optional[TradeExecution] = None
    realized_pnl: Optional[Decimal] = None
    exit_reason: Optional[str] = None
    status: str = "open" # 'open', 'closed', 'cancelled', 'rejected'


class TradeDecisionSnapshot(BaseModel):
    """Snapshot of decision context used by router and arb coordinator."""
    agent_id: str
    symbol: str
    side: str
    quantity: float
    signal_type: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    meta_signals: list[Any] = Field(default_factory=list)
    governor_limit: float | None = None

    def to_trade_decision(self) -> TradeDecision:
        return TradeDecision(
            agent_name=self.agent_id,
            symbol=self.symbol,
            direction=self.side,
            confidence=self.confidence,
            reasoning=self.reasoning,
            metadata={"signal_type": self.signal_type, "meta_signals": self.meta_signals},
        )


class TradeExecutionLog(BaseModel):
    """Lightweight execution log used by router and arb coordinator."""
    order_id: str
    broker_id: str = ""
    fill_quantity: float = 0.0
    status: str = "pending"

    def to_trade_execution(self) -> TradeExecution | None:
        if self.status == "pending" and self.fill_quantity == 0.0:
            return None
        return TradeExecution(
            order_id=self.order_id,
            account_id=self.broker_id,
            filled_quantity=Decimal(str(self.fill_quantity)),
            avg_fill_price=Decimal("0"),
        )
