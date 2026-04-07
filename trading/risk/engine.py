# risk/engine.py
from __future__ import annotations
import logging
import asyncio
from typing import TYPE_CHECKING

from broker.models import OrderBase, Quote
from risk.kill_switch import KillSwitch
from risk.rules import PortfolioContext, RiskResult, RiskRule

if TYPE_CHECKING:
    from risk.governor import CapitalGovernor

logger = logging.getLogger(__name__)


class RiskEngine:
    def __init__(
        self,
        rules: list[RiskRule],
        kill_switch: KillSwitch,
        governor: CapitalGovernor | None = None,
    ) -> None:
        self._rules = rules
        self._kill_switch = kill_switch
        self._governor = governor
        self._kill_active: bool = False
        self._brokers: dict = {}

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

    @property
    def rules(self) -> list[RiskRule]:
        return self._rules

    def register_brokers(self, brokers: dict) -> None:
        """Register all active brokers for kill-switch cancellation."""
        self._brokers = brokers

    def check_kill_active(self) -> bool:
        """Return True if kill switch has been triggered (blocks order submissions)."""
        return self._kill_active or self._kill_switch.is_enabled

    async def trigger_kill_switch(self, reason: str = "") -> None:
        """Two-phase kill switch: block submissions first, then cancel across all brokers."""
        # Phase 1: Block all new order submissions immediately
        self._kill_active = True
        self._kill_switch.enable(reason)
        logger.warning("Kill switch triggered: %s", reason)

        # Phase 2: Cancel open orders across all registered brokers
        for broker_name, broker in self._brokers.items():
            try:
                if hasattr(broker, "orders") and hasattr(
                    broker.orders, "cancel_all_orders"
                ):
                    await broker.orders.cancel_all_orders()
                    logger.info("Cancelled all orders on broker: %s", broker_name)
            except Exception as exc:
                logger.warning(
                    "Failed to cancel orders on broker %s: %s", broker_name, exc
                )

    async def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        return await self.evaluate_order(trade, quote, ctx)

    async def evaluate_order(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        if self._kill_active or self._kill_switch.is_enabled:
            return RiskResult(
                passed=False,
                rule_name="kill_switch",
                reason=f"Kill switch is enabled: {self._kill_switch.reason}",
            )

        final_result = RiskResult(passed=True)

        for rule in self._rules:
            # Handle rules that have async_evaluate (like Governor) vs sync evaluate
            if hasattr(rule, "async_evaluate"):
                result = await rule.async_evaluate(trade, quote, ctx)
            elif asyncio.iscoroutinefunction(rule.evaluate):
                result = await rule.evaluate(trade, quote, ctx)
            else:
                result = rule.evaluate(trade, quote, ctx)

            if not result.passed:
                logger.info("Risk rule %s blocked trade: %s", rule.name, result.reason)
                # Auto-trigger kill switch if rule specifies it
                if hasattr(rule, "action") and rule.action == "kill_switch":
                    self._kill_switch.enable(
                        f"Triggered by {rule.name}: {result.reason}"
                    )
                return result

            # If rule suggests a smaller quantity, apply it and continue
            if result.adjusted_quantity is not None:
                if (
                    final_result.adjusted_quantity is None
                    or result.adjusted_quantity < final_result.adjusted_quantity
                ):
                    final_result.adjusted_quantity = result.adjusted_quantity
                    # Update the trade quantity for subsequent rules to evaluate the NEW size
                    trade.quantity = result.adjusted_quantity

        return final_result

    async def evaluate_portfolio(self, portfolio_ctx: Any) -> bool:
        """Portfolio-level risk checks (e.g. max gross exposure, diversification)."""
        # Placeholder for future portfolio rules
        return True

    async def evaluate_strategy(self, strategy_name: str, metrics: dict) -> bool:
        """Strategy-level risk checks (e.g. max drawdown per strategy, consecutive losses)."""
        # Placeholder for future strategy rules
        return True
