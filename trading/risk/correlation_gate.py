from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Any, TYPE_CHECKING

from risk.rules import RiskRule, RiskResult, PortfolioContext

if TYPE_CHECKING:
    from broker.models import OrderBase, Quote


@dataclass
class CorrelationGate(RiskRule):
    """Reduces position size when portfolio correlation is high."""

    name: ClassVar[str] = "correlation_gate"

    correlation_monitor: Any = None
    high_correlation_threshold: float = 0.7
    critical_correlation_threshold: float = 0.85
    high_correlation_multiplier: float = 0.5
    critical_correlation_multiplier: float = 0.25

    async def async_evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        if not self.correlation_monitor:
            return RiskResult(
                passed=True,
                rule_name=self.name,
                reason="Correlation monitor not configured",
            )

        snapshot = await self.correlation_monitor.get_latest_snapshot()
        if not snapshot:
            return RiskResult(
                passed=True, rule_name=self.name, reason="No correlation data"
            )

        agent_name = getattr(trade, "agent_name", None)
        if not agent_name:
            return RiskResult(
                passed=True, rule_name=self.name, reason="Agent name not available"
            )

        should_reduce, multiplier = self.correlation_monitor.should_reduce_position(
            agent_name, snapshot
        )

        if should_reduce:
            adjusted_qty = Decimal(str(float(trade.quantity) * multiplier))
            return RiskResult(
                passed=True,
                rule_name=self.name,
                adjusted_quantity=adjusted_qty,
                reason=f"Correlation gate: reducing size by {(1 - multiplier) * 100:.0f}%",
            )

        return RiskResult(passed=True, rule_name=self.name)

    def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        return RiskResult(passed=True, rule_name=self.name, reason="Use async_evaluate")
