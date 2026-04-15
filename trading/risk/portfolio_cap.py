"""Portfolio-level position ceiling enforced before any new trade."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class _BrokerLike(Protocol):
    async def total_position_usd(self) -> Decimal: ...


class PortfolioCapExceeded(Exception):
    """Raised when a proposed trade would push portfolio exposure over cap."""


class PortfolioCap:
    """Enforces a single USD ceiling across every wired broker.

    A cap of 0 disables the check (useful for backtests / paper).
    """

    def __init__(self, max_usd: Decimal, brokers: dict[str, _BrokerLike]) -> None:
        self._max = max_usd
        self._brokers = brokers

    async def check(self, additional_usd: Decimal) -> None:
        if self._max <= 0:
            return
        total = Decimal("0")
        for b in self._brokers.values():
            total += await b.total_position_usd()
        if total + additional_usd > self._max:
            raise PortfolioCapExceeded(
                f"would push portfolio to ${total + additional_usd} (cap ${self._max})"
            )
