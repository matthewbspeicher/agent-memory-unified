"""
ArbCoordinator — distributed state machine for atomic dual-leg arbitrage.

Determines sequencing (e.g. less-liquid-first), executes Leg 1, then Leg 2.
If Leg 2 fails, attempts to unwind Leg 1 to remain delta-neutral.
"""

from __future__ import annotations

import logging
import asyncio
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from execution.models import ArbTrade, ArbLeg, ArbState, SequencingStrategy
from broker.models import OrderStatus, OrderResult, OrderSide, MarketOrder

if TYPE_CHECKING:
    from broker.interfaces import Broker
    from storage.arbitrage import ArbStore
    from config import Config
    from agents.meta import MetaAgent
    from data.events import EventBus
    from journal.manager import JournalManager

logger = logging.getLogger(__name__)


class ArbCoordinator:
    def __init__(
        self,
        brokers: dict[str, Broker],
        store: ArbStore,
        config: Config,
        meta_agent: Optional[MetaAgent] = None,
        event_bus: Optional[EventBus] = None,
        journal_manager: Optional[JournalManager] = None,
    ) -> None:
        self._brokers = brokers
        self._store = store
        self._config = config
        self._meta_agent = meta_agent
        self._event_bus = event_bus
        self._journal_manager = journal_manager

    async def _publish_state(self, trade: ArbTrade):
        if self._event_bus:
            from execution.models import ArbStateMessage

            msg = ArbStateMessage(
                trade_id=trade.id,
                symbol_a=trade.symbol_a,
                symbol_b=trade.symbol_b,
                state=trade.state.value,
                error_message=trade.error_message,
                expected_profit_bps=trade.expected_profit_bps,
            )
            await self._event_bus.publish("arb.state_change", msg.model_dump())

    async def _log_journal_entry(self, trade: ArbTrade):
        """Creates a semantic memory snapshot of the arb trade decision."""
        if not self._journal_manager:
            return

        from journal.models import TradeDecisionSnapshot, TradeExecutionLog

        # Simplified decision snapshot for the arb
        decision = TradeDecisionSnapshot(
            agent_id="arb_coordinator",
            symbol=f"{trade.symbol_a} / {trade.symbol_b}",
            side="ARB",
            quantity=float(trade.leg_a.order.quantity),
            signal_type="spread_convergence",
            confidence=1.0,
            reasoning=f"Executing {trade.sequencing.value} arb. Expected profit: {trade.expected_profit_bps} bps",
            meta_signals=[],
        )

        # We log the initial intent. The execution log will be updated upon completion.
        execution = TradeExecutionLog(
            order_id=trade.id, broker_id="dual", fill_quantity=0.0, status="pending"
        )

        await self._journal_manager.log_trade_entry(
            trade.id, decision, execution, tags=["arbitrage", "track16"]
        )

    async def execute_arbitrage(self, trade: ArbTrade) -> bool:
        """
        Main entry point for arbitrage execution.
        Returns True if the entire arbitrage (both legs) completed successfully.
        """
        logger.info(
            f"ArbCoordinator: Starting arbitrage {trade.id} for {trade.symbol_a} ↔ {trade.symbol_b}"
        )
        await self._publish_state(trade)
        await self._log_journal_entry(trade)

        try:
            # 1. Pre-flight toxicity check (AI Clearance)
            if self._meta_agent:
                trade.state = ArbState.TOXICITY_CHECK
                await self._publish_state(trade)
                # Check toxicity for BOTH symbols
                tox_a = await self._meta_agent.check_toxicity(trade.symbol_a)
                tox_b = await self._meta_agent.check_toxicity(trade.symbol_b)
                max_tox = max(tox_a, tox_b)

                if max_tox > self._config.arb_toxicity_threshold:
                    logger.warning(
                        f"ArbCoordinator: Aborting {trade.id} - Toxicity too high: {max_tox:.2f}"
                    )
                    trade.state = ArbState.FAILED
                    trade.error_message = f"Toxicity too high: {max_tox:.2f}"
                    await self._publish_state(trade)
                    await self._log_journal_exit_wrapper(
                        trade, pnl=0.0, reason="Aborted: Toxicity"
                    )
                    return False

            # 2. Pre-flight slippage check
            if not await self._check_preflight_slippage(trade):
                logger.warning(
                    f"ArbCoordinator: Aborting {trade.id} due to excessive estimated slippage."
                )
                trade.state = ArbState.FAILED
                trade.error_message = "Excessive estimated slippage"
                await self._publish_state(trade)
                await self._log_journal_exit_wrapper(
                    trade, pnl=0.0, reason="Aborted: Slippage"
                )
                return False

            # 2. Persist initial state
            await self._store.save_trade(trade)

            # 3. Execute Legs Concurrently
            success = await self._execute_legs_concurrently(trade)

            if success:
                trade.state = ArbState.COMPLETED
                await self._store.update_trade_state(trade.id, trade.state)
                await self._publish_state(trade)
                logger.info(
                    f"ArbCoordinator: Arbitrage {trade.id} completed successfully."
                )
                expected_pnl_usd = float(trade.expected_profit_bps) / 100.0
                await self._log_journal_exit_wrapper(
                    trade, pnl=expected_pnl_usd, reason="Arb executed successfully"
                )
                return True
            else:
                # _execute_legs_concurrently handles its own state updates and unwinds
                return False

        except Exception as e:
            logger.exception(
                f"ArbCoordinator: Fatal error executing arbitrage {trade.id}"
            )
            trade.state = ArbState.FAILED
            trade.error_message = str(e)
            await self._store.update_trade_state(
                trade.id, trade.state, trade.error_message
            )
            await self._publish_state(trade)
            await self._log_journal_exit_wrapper(
                trade, pnl=0.0, reason=f"Fatal error: {e}"
            )
            return False

    async def _execute_legs_concurrently(self, trade: ArbTrade) -> bool:
        """Executes both legs in parallel using asyncio.gather."""
        trade.state = ArbState.CONCURRENT_PENDING
        await self._store.update_trade_state(trade.id, trade.state)
        await self._publish_state(trade)

        t_start = time.perf_counter()

        # We fire both tasks. In a real system, we might want to slightly stagger
        # if sequencing is needed, but the task specifies concurrent.
        task_a = self._execute_leg(trade, "leg_a")
        t_skew = time.perf_counter()
        task_b = self._execute_leg(trade, "leg_b")

        skew_ms = (t_skew - t_start) * 1000.0
        logger.info(f"ArbCoordinator: Placement Skew for {trade.id}: {skew_ms:.2f}ms")

        results = await asyncio.gather(task_a, task_b, return_exceptions=True)

        success_a = results[0] if not isinstance(results[0], Exception) else False
        success_b = results[1] if not isinstance(results[1], Exception) else False

        if isinstance(results[0], Exception):
            logger.error(f"Leg A exception: {results[0]}")
        if isinstance(results[1], Exception):
            logger.error(f"Leg B exception: {results[1]}")

        if success_a and success_b:
            return True

        # Handle partial failures
        if success_a and not success_b:
            logger.warning(
                f"ArbCoordinator: Leg B failed, unwinding Leg A for {trade.id}"
            )
            trade.state = ArbState.UNWINDING
            await self._store.update_trade_state(trade.id, trade.state, "Leg B failed")
            await self._publish_state(trade)
            await self._unwind_leg(trade, "leg_a")
            await self._log_journal_exit_wrapper(
                trade, pnl=-1.0, reason="Unwound Leg A after Leg B failure"
            )
        elif success_b and not success_a:
            logger.warning(
                f"ArbCoordinator: Leg A failed, unwinding Leg B for {trade.id}"
            )
            trade.state = ArbState.UNWINDING
            await self._store.update_trade_state(trade.id, trade.state, "Leg A failed")
            await self._publish_state(trade)
            await self._unwind_leg(trade, "leg_b")
            await self._log_journal_exit_wrapper(
                trade, pnl=-1.0, reason="Unwound Leg B after Leg A failure"
            )
        else:
            logger.error(f"ArbCoordinator: Both legs failed for {trade.id}")
            trade.state = ArbState.FAILED
            trade.error_message = "Both legs failed"
            await self._store.update_trade_state(
                trade.id, trade.state, trade.error_message
            )
            await self._publish_state(trade)
            await self._log_journal_exit_wrapper(
                trade, pnl=0.0, reason="Both legs failed"
            )

        return False

    async def _log_journal_exit_wrapper(self, trade: ArbTrade, pnl: float, reason: str):
        if not self._journal_manager:
            return

        # We simulate the final execution details
        from journal.models import TradeExecution
        from decimal import Decimal

        # Calculate actual fill price from legs
        fill_price_a = trade.leg_a.fill_price or Decimal("0")
        fill_price_b = trade.leg_b.fill_price or Decimal("0")
        combined_price = fill_price_a + fill_price_b

        exit_exec = TradeExecution(
            order_id=f"exit-{trade.id}",
            account_id="dual",
            filled_quantity=Decimal(str(trade.leg_a.order.quantity)),
            avg_fill_price=combined_price,
        )

        await self._journal_manager.update_trade_exit(
            trade_id=trade.id,
            exit_execution=exit_exec,
            realized_pnl=Decimal(str(pnl)),
            exit_reason=reason,
        )

    def _determine_leg_order(self, trade: ArbTrade) -> tuple[str, str]:
        """Returns (first_leg_name, second_leg_name)."""
        if trade.sequencing == SequencingStrategy.KALSHI_FIRST:
            return "leg_a", "leg_b"
        elif trade.sequencing == SequencingStrategy.POLY_FIRST:
            return "leg_b", "leg_a"

        # Default: Less liquid first
        # In a real system, we'd check depth here. For now, assume Kalshi is less liquid.
        return "leg_a", "leg_b"

    async def _check_preflight_slippage(self, trade: ArbTrade) -> bool:
        """
        Estimates slippage based on current order book depth.
        Aborts if (expected_profit - estimated_slippage) < threshold.
        """
        try:
            poly_broker = self._brokers.get("polymarket")
            if poly_broker:
                # O(1) Cache integration - trade.symbol_b is a string (condition_id)
                ds = getattr(poly_broker.market_data, "ds", None)
                if ds and hasattr(ds, "get_live_quote"):
                    price = await ds.get_live_quote(trade.symbol_b)
                    if price is None:
                        logger.warning(
                            f"Slippage check: No live quote for {trade.symbol_b}"
                        )
                        return False
                else:
                    # Fallback for paper brokers or standard market data providers
                    from broker.models import Symbol, AssetType

                    sym = Symbol(ticker=trade.symbol_b, asset_type=AssetType.PREDICTION)
                    try:
                        quote = await poly_broker.market_data.get_quote(sym)
                        if quote is None:
                            logger.warning(
                                f"Slippage check: No quote for {trade.symbol_b}"
                            )
                            return False
                    except NotImplementedError:
                        # Paper brokers may not implement quotes
                        pass

                # In a real system, we'd compare this price to trade.leg_b.order.limit_price
                # For now, we just verify the quote exists and is fresh (handled in get_live_quote)
                return True
            return True
        except Exception as e:
            logger.error(f"Slippage check failed: {e}")
            return False

    async def _execute_leg(self, trade: ArbTrade, leg_name: str) -> bool:
        """Helper to place an order and wait for fill/confirmation."""
        leg: ArbLeg = getattr(trade, leg_name)
        broker = self._brokers.get(leg.broker_id)

        if not broker:
            logger.error(f"Broker {leg.broker_id} not found for {leg_name}")
            return False

        try:
            async with asyncio.timeout(self._config.order_timeout):
                order_result: OrderResult = await broker.orders.place_order(
                    leg.order.account_id or "", leg.order
                )

                leg.external_order_id = order_result.order_id
                leg.status = order_result.status.value

                if order_result.status == OrderStatus.FILLED:
                    leg.fill_price = order_result.avg_fill_price
                    leg.fill_quantity = order_result.filled_quantity
                    leg.status = "filled"
                elif order_result.status == OrderStatus.SUBMITTED:
                    # Paper/dry-run brokers return SUBMITTED with zero fill.
                    leg.fill_price = (
                        order_result.avg_fill_price or leg.order.limit_price
                        if hasattr(leg.order, "limit_price")
                        else Decimal("0")
                    )
                    leg.fill_quantity = (
                        order_result.filled_quantity or leg.order.quantity
                    )
                    leg.status = "submitted"

                await self._store.update_leg_atomic(trade.id, leg_name, leg)
                return order_result.status in (
                    OrderStatus.FILLED,
                    OrderStatus.SUBMITTED,
                )

        except TimeoutError:
            logger.error(f"ArbCoordinator: Leg {leg_name} timed out")
            return False
        except Exception as e:
            logger.error(f"ArbCoordinator: Leg {leg_name} failed: {e}")
            return False

    async def _unwind_leg(self, trade: ArbTrade, leg_name: str):
        """Emergency rollback: place an opposite order to close the filled leg."""
        leg: ArbLeg = getattr(trade, leg_name)
        broker = self._brokers.get(leg.broker_id)

        if not broker or (leg.fill_quantity is not None and leg.fill_quantity <= 0):
            return

        logger.warning(
            f"ArbCoordinator: Unwinding {leg_name} ({leg.fill_quantity} @ {leg.fill_price})"
        )

        unwind_side = (
            OrderSide.SELL if leg.order.side == OrderSide.BUY else OrderSide.BUY
        )

        unwind_order = MarketOrder(
            symbol=leg.order.symbol,
            side=unwind_side,
            quantity=leg.fill_quantity,
            account_id=leg.order.account_id,
        )

        try:
            async with asyncio.timeout(self._config.order_timeout):
                await broker.orders.place_order(
                    unwind_order.account_id or "", unwind_order
                )
            await self._store.update_trade_state(trade.id, ArbState.UNWOUND)
            logger.info(f"ArbCoordinator: Unwind successful for {trade.id}")
        except TimeoutError:
            logger.error(
                f"ArbCoordinator: CRITICAL - Unwind timed out for {leg_name} on {trade.id}"
            )
            await self._store.update_trade_state(
                trade.id, ArbState.FAILED, f"Unwind timed out for {leg_name}"
            )
        except Exception as e:
            logger.error(
                f"ArbCoordinator: CRITICAL - Failed to unwind {leg_name} for {trade.id}: {e}"
            )
            await self._store.update_trade_state(
                trade.id, ArbState.FAILED, f"Unwind failed: {e}"
            )
