# risk/engine.py
from __future__ import annotations
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

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
        *,
        configuration_error: str | None = None,
    ) -> None:
        self._configuration_error = configuration_error
        self._rules = rules
        self._kill_switch = kill_switch
        self._governor = governor
        self._control_store = None
        self._control_fault = False
        self._control_lock = asyncio.Lock()
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
        return (
            bool(self._configuration_error)
            or self._kill_switch.is_enabled
            or self._control_fault
        )

    def bind_control_store(self, store) -> None:
        self._control_store = store

    async def initialize_control(self) -> None:
        """Restore the persisted halt before starting execution workers."""
        try:
            if self._control_store is None:
                raise RuntimeError("Trading control store is unavailable")
            # Missing control state is not evidence of permission to trade.
            # A configured halt also takes precedence over a stale persisted resume.
            if self._kill_switch.is_enabled:
                await self._control_store.set("kill_switch:active", "true")
            else:
                await self._control_store.set("kill_switch:active", "true", nx=True)
            await self.sync_halt()
        except Exception:
            self._control_fault = True
            self._kill_switch.enable("Trading control state unavailable")
            raise

    async def sync_halt(self) -> None:
        async with self._control_lock:
            await self._sync_halt_locked()

    async def _sync_halt_locked(self) -> None:
        if self._configuration_error:
            raise RuntimeError(self._configuration_error)
        if self._control_fault:
            raise RuntimeError("Trading control requires explicit recovery")
        if self._control_store is not None:
            value = await self._control_store.get("kill_switch:active")
            if value in ("true", b"true"):
                self._kill_switch.enable(
                    self._kill_switch.reason or "Persisted trading halt"
                )
            elif value in ("false", b"false"):
                self._kill_switch.disable()
            else:
                raise RuntimeError("Trading control state missing or invalid")

    @asynccontextmanager
    async def dispatch_guard(self):
        """Serialize the final halt check and transport against local halt updates."""
        async with self._control_lock:
            await self._sync_halt_locked()
            if self.check_kill_active():
                raise RuntimeError("Trading is halted")
            yield

    async def set_halted(self, enabled: bool, reason: str = "") -> list[str]:
        """Persist control changes before acknowledging them; cancellation remains available.

        A failed halt write leaves this process blocked. A failed resume never
        clears its local halt. Explicit successful recovery clears control faults.
        """
        async with self._control_lock:
            if not enabled and self._configuration_error:
                raise RuntimeError(self._configuration_error)
            if enabled:
                self._kill_switch.enable(reason)
            try:
                if self._control_store is not None:
                    await self._control_store.set(
                        "kill_switch:active", "true" if enabled else "false"
                    )
                self._control_fault = False
                self._kill_switch.toggle(enabled, reason)
            except Exception:
                self._control_fault = True
                self._kill_switch.enable("Trading control persistence failed")
                if enabled:
                    await self._cancel_open_orders()
                raise
            return await self._cancel_open_orders() if enabled else []

    async def _cancel_open_orders(self) -> list[str]:
        failures = []
        for broker_name, broker in self._brokers.items():
            try:
                await asyncio.wait_for(broker.orders.cancel_all_orders(), timeout=10)
            except Exception:
                failures.append(broker_name)
                logger.exception("Failed to cancel orders on broker %s", broker_name)
        return failures

    async def trigger_kill_switch(self, reason: str = "") -> list[str]:
        return await self.set_halted(True, reason)

    async def evaluate(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        return await self.evaluate_order(trade, quote, ctx)

    async def evaluate_order(
        self, trade: OrderBase, quote: Quote, ctx: PortfolioContext
    ) -> RiskResult:
        try:
            await self.sync_halt()
        except Exception:
            return RiskResult(
                passed=False,
                rule_name="kill_switch",
                reason="Trading control state unavailable",
            )
        if self.check_kill_active():
            return RiskResult(
                passed=False,
                rule_name="kill_switch",
                reason=f"Kill switch is enabled: {self._kill_switch.reason}",
            )

        final_result = RiskResult(passed=True)
        original_quantity = trade.quantity
        constraint_rules = []

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
                    try:
                        await self.trigger_kill_switch(
                            f"Triggered by {rule.name}: {result.reason}"
                        )
                    except Exception:
                        logger.exception(
                            "Could not persist automatic halt; local execution remains blocked"
                        )
                return result

            if result.adjusted_quantity is None:
                constraint_rules.append(rule)
            # If rule suggests a smaller quantity, apply it and continue
            if result.adjusted_quantity is not None:
                if (
                    final_result.adjusted_quantity is None
                    or result.adjusted_quantity < final_result.adjusted_quantity
                ):
                    final_result.adjusted_quantity = result.adjusted_quantity
                    # Update the trade quantity for subsequent rules to evaluate the NEW size
                    trade.quantity = result.adjusted_quantity

        # Reducing an offsetting order can INCREASE projected exposure. Recheck
        # constraints already evaluated before a later sizing rule changed terms.
        # Sizing proposals themselves are applied only once.
        if trade.quantity != original_quantity:
            for rule in constraint_rules:
                if hasattr(rule, "async_evaluate"):
                    result = await rule.async_evaluate(trade, quote, ctx)
                elif asyncio.iscoroutinefunction(rule.evaluate):
                    result = await rule.evaluate(trade, quote, ctx)
                else:
                    result = rule.evaluate(trade, quote, ctx)
                if not result.passed:
                    return result
        return final_result

    async def evaluate_portfolio(self, portfolio_ctx: Any) -> bool:
        """Portfolio-level risk checks (e.g. max gross exposure, diversification)."""
        # Placeholder for future portfolio rules
        return True

    async def evaluate_strategy(self, strategy_name: str, metrics: dict) -> bool:
        """Strategy-level risk checks (e.g. max drawdown per strategy, consecutive losses)."""
        # Placeholder for future strategy rules
        return True
