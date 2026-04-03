from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Optional
from decimal import Decimal

from broker.models import OrderBase
from pydantic import BaseModel, Field as PydanticField

class ArbState(Enum):
    INIT = "init"
    TOXICITY_CHECK = "toxicity_check"
    LEG_A_PENDING = "leg_a_pending"
    LEG_A_FILLED = "leg_a_filled"
    LEG_B_PENDING = "leg_b_pending"
    LEG_B_FILLED = "leg_b_filled"
    CONCURRENT_PENDING = "concurrent_pending"
    COMPLETED = "completed"
    LEG_A_FAILED = "leg_a_failed"
    LEG_B_FAILED = "leg_b_failed"
    UNWINDING = "unwinding"
    UNWOUND = "unwound"
    FAILED = "failed"

class SequencingStrategy(Enum):
    LESS_LIQUID_FIRST = "less_liquid_first"
    KALSHI_FIRST = "kalshi_first"
    POLY_FIRST = "poly_first"

@dataclass
class ArbLeg:
    broker_id: str
    order: OrderBase
    fill_price: Optional[Decimal] = None
    fill_quantity: Decimal = Decimal("0")
    status: str = "pending"
    external_order_id: Optional[str] = None

@dataclass
class ArbTrade:
    id: str
    symbol_a: str
    symbol_b: str
    leg_a: ArbLeg
    leg_b: ArbLeg
    expected_profit_bps: int
    sequencing: SequencingStrategy = SequencingStrategy.LESS_LIQUID_FIRST
    state: ArbState = ArbState.INIT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialization for SQLite storage."""
        return {
            "id": self.id,
            "symbol_a": self.symbol_a,
            "symbol_b": self.symbol_b,
            "expected_profit_bps": self.expected_profit_bps,
            "sequencing": self.sequencing.value,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message
        }

class ArbStateMessage(BaseModel):
    trade_id: str
    symbol_a: str
    symbol_b: str
    state: str
    timestamp: datetime = PydanticField(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None
    expected_profit_bps: Optional[int] = None
