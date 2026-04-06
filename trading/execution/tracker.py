"""ExecutionTracker — records fill slippage for executed trades."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class ExecutionFill:
    """Represents a single order fill with slippage measurement."""

    opportunity_id: str
    agent_name: str
    broker_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    expected_price: Decimal
    actual_price: Decimal
    quantity: Decimal
    filled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def slippage_bps(self) -> float:
        """
        Slippage in basis points (positive = worse execution, negative = better).

        For BUY: positive means filled above expected (paid more).
        For SELL: positive means filled below expected (received less).
        """
        if not self.expected_price or self.expected_price == 0:
            return 0.0
        raw_diff = self.actual_price - self.expected_price
        if self.side == "SELL":
            raw_diff = -raw_diff  # Invert: filling below expected is worse for seller
        return float(raw_diff / self.expected_price * 10000)

    def to_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "agent_name": self.agent_name,
            "broker_id": self.broker_id,
            "symbol": self.symbol,
            "side": self.side,
            "expected_price": str(self.expected_price),
            "actual_price": str(self.actual_price),
            "quantity": str(self.quantity),
            "slippage_bps": self.slippage_bps,
            "filled_at": self.filled_at.isoformat(),
        }


class ExecutionTracker:
    """
    Records execution quality (slippage) for each trade fill.
    Maintains in-memory fills per agent and persists to store if provided.
    """

    def __init__(self, store=None) -> None:
        self._store = store
        self._fills: dict[str, list[ExecutionFill]] = {}

    async def record_fill(
        self,
        opportunity_id: str,
        agent_name: str,
        broker_id: str,
        expected_price: Decimal,
        actual_price: Decimal,
        quantity: Decimal,
        side: str,
        symbol: str,
    ) -> ExecutionFill:
        """Record a fill and compute slippage."""
        fill = ExecutionFill(
            opportunity_id=opportunity_id,
            agent_name=agent_name,
            broker_id=broker_id,
            symbol=symbol,
            side=side,
            expected_price=expected_price,
            actual_price=actual_price,
            quantity=quantity,
        )

        # Track in memory
        if agent_name not in self._fills:
            self._fills[agent_name] = []
        self._fills[agent_name].append(fill)

        # Persist to store
        if self._store:
            try:
                await self._store.save(fill)
            except Exception as exc:
                logger.warning("Failed to persist fill for %s: %s", opportunity_id, exc)

        logger.debug(
            "Fill recorded: %s %s %s — expected=%s actual=%s slippage=%.1f bps",
            agent_name,
            side,
            symbol,
            expected_price,
            actual_price,
            fill.slippage_bps,
        )
        return fill

    def get_fills(self, agent_name: str) -> list[ExecutionFill]:
        """Return all in-memory fills for an agent."""
        return list(self._fills.get(agent_name, []))

    def get_recent_fills(
        self,
        agent_name: str,
        limit: int = 20,
        max_days: int | None = None,
    ) -> list[ExecutionFill]:
        """Return up to *limit* most-recent fills for an agent.

        Args:
            agent_name: Agent whose fills to retrieve.
            limit:      Maximum number of fills to return (most-recent first).
            max_days:   If set, exclude fills older than this many days.
        """
        fills = self._fills.get(agent_name, [])
        if max_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
            fills = [
                f
                for f in fills
                if (
                    f.filled_at
                    if f.filled_at.tzinfo
                    else f.filled_at.replace(tzinfo=timezone.utc)
                )
                >= cutoff
            ]
        # Most-recent first, then cap to limit
        return list(reversed(fills[-limit:]))

    def average_slippage_bps(self, agent_name: str) -> float:
        """Return the average slippage in bps for an agent."""
        fills = self._fills.get(agent_name, [])
        if not fills:
            return 0.0
        return sum(f.slippage_bps for f in fills) / len(fills)
