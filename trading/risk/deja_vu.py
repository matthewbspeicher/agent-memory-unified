import logging

from broker.models import OrderBase, Quote
from risk.rules import RiskRule, RiskResult, PortfolioContext
from journal.manager import JournalManager

logger = logging.getLogger(__name__)


class DejaVuGuard(RiskRule):
    """
    Checks the semantic trading journal to prevent repeating past mistakes.
    Queries the JournalManager for similar trades on the same symbol/direction.
    """

    name = "deja_vu_guard"

    def __init__(
        self, journal_manager: JournalManager, max_similar_losses: int = 3
    ) -> None:
        self._journal_manager = journal_manager
        self.max_similar_losses = max_similar_losses

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        """Synchronous evaluation - not supported for async guard."""
        return RiskResult(
            passed=True,
            rule_name=self.name,
            reason="DejaVuGuard requires async evaluation",
            adjusted_quantity=trade.quantity,
        )

    async def async_evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        try:
            # Query recent trades chronologically
            direction = (
                trade.side.value if hasattr(trade.side, "value") else str(trade.side)
            )
            results = await self._journal_manager.get_recent_trades(
                trade.symbol.ticker, limit=20
            )

            consecutive_losses = 0

            for result in results:
                metadata = result.get("metadata", {})
                status = metadata.get("status")
                pnl = metadata.get("realized_pnl")

                # Check if it was the same direction
                decision = metadata.get("decision", {})
                if decision.get("direction") != direction:
                    continue

                if status == "closed" and pnl is not None and pnl < 0:
                    consecutive_losses += 1
                elif status == "closed" and pnl is not None and pnl > 0:
                    # Break the streak if there was a winning trade
                    break

                if consecutive_losses >= self.max_similar_losses:
                    return RiskResult(
                        passed=False,
                        rule_name=self.name,
                        reason=f"Deja Vu: Prevented trade due to {consecutive_losses} consecutive historical losses for {trade.symbol.ticker} {direction}",
                    )

            return RiskResult(passed=True, rule_name=self.name)

        except Exception as e:
            logger.error(f"DejaVuGuard failed to evaluate: {e}")
            # Fail-open if the memory system is unavailable
            return RiskResult(passed=True, rule_name=self.name)
