"""Durable dispatch identity and authoritative reconciliation contracts."""

from dataclasses import dataclass
from datetime import datetime

from broker.models import OrderBase
from execution.context import OrderSnapshot


@dataclass(frozen=True)
class DispatchEvidence:
    dispatch_id: str
    account_id: str
    operation: str
    order: OrderBase
    original_order_id: str | None
    epoch: str
    observed_at: datetime
    outcome: str  # applied or not_accepted; never inferred from empty history
    snapshot: OrderSnapshot | None = None
    final: bool = True  # acceptance is final, even if a resulting order remains open
