from __future__ import annotations
from broker.models import OrderStatus

STATUS_MAP = {
    "pending": OrderStatus.SUBMITTED,
    "open": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIAL,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.CANCELLED,
}
