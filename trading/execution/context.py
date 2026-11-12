"""Authoritative, account-scoped inputs to execution admission."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from broker.models import OrderBase, OrderStatus
from risk.rules import PortfolioContext


@dataclass
class OrderSnapshot:
    order_id: str
    order: OrderBase
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    submitted_at: datetime | None = None


@dataclass
class AccountRiskState:
    context: PortfolioContext
    observed_at: datetime
    orders: list[OrderSnapshot]
    source: str
    complete: bool = True
    terminal_order_ids: set[str] = field(default_factory=set)
    symbol_identity: str = "full"
    epoch: str = ""
    exposure_observed_at: datetime | None = None
