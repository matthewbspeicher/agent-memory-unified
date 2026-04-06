"""Trust-aware position sizing engine using Kelly criterion."""

from __future__ import annotations
import logging
from decimal import Decimal

from agents.models import TrustLevel
from sizing.kelly import compute_position_size

logger = logging.getLogger(__name__)

# Kelly multiplier per trust level: more trust → larger fraction of Kelly
TRUST_KELLY: dict[TrustLevel, Decimal] = {
    TrustLevel.MONITORED: Decimal("0.25"),
    TrustLevel.ASSISTED: Decimal("0.375"),
    TrustLevel.AUTONOMOUS: Decimal("0.50"),
}


class SizingEngine:
    """Computes position sizes scaled by agent trust level and historical performance."""

    def __init__(
        self,
        perf_store,
        min_trades: int = 30,
        max_pct: Decimal = Decimal("0.10"),
    ) -> None:
        self._perf = perf_store
        self._min_trades = min_trades
        self._max_pct = max_pct

    async def compute_size(
        self,
        agent_name: str,
        trust_level: TrustLevel,
        price: Decimal,
        bankroll: Decimal,
    ) -> Decimal:
        """Return recommended quantity in shares.

        Falls back to 1 share when there is insufficient performance data.
        """
        snap = await self._perf.get_latest(agent_name)
        if not snap or snap.total_trades < self._min_trades:
            logger.debug(
                "Insufficient data for %s (%d trades), returning minimum size=1",
                agent_name,
                snap.total_trades if snap else 0,
            )
            return Decimal("1")

        mult = TRUST_KELLY.get(trust_level, Decimal("0.25"))
        qty = compute_position_size(
            win_rate=snap.win_rate,
            avg_win=abs(snap.avg_win) if snap.avg_win else Decimal("0"),
            avg_loss=abs(snap.avg_loss) if snap.avg_loss else Decimal("0"),
            bankroll=bankroll,
            price=price,
            kelly_multiplier=mult,
            max_pct=self._max_pct,
        )
        return max(qty, Decimal("1"))
