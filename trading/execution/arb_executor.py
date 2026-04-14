"""ArbExecutor — auto-executes arbitrage when spreads exceed threshold."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from execution.cost_model import CostModel

if TYPE_CHECKING:
    from data.events import EventBus
    from storage.spreads import SpreadStore
    from execution.arbitrage import ArbCoordinator
    from broker.models import Symbol

logger = logging.getLogger(__name__)


class ArbExecutor:
    """Subscribes to arb.spread events and auto-executes profitable opportunities."""

    def __init__(
        self,
        spread_store: SpreadStore,
        arb_coordinator: ArbCoordinator,
        event_bus: EventBus,
        cost_model: CostModel | None = None,
        min_profit_bps: float = 5.0,
        max_position_usd: float = 100.0,
        enabled: bool = False,
    ) -> None:
        self._store = spread_store
        self._coordinator = arb_coordinator
        self._bus = event_bus
        self._cost_model = cost_model or CostModel()
        self._min_profit_bps = min_profit_bps
        self._max_position_usd = max_position_usd
        self._enabled = enabled
        self._active_trades: dict[str, bool] = {}

    async def run(self) -> None:
        """Subscribe to spread events and execute when profitable."""
        logger.info(
            "ArbExecutor: Starting (enabled=%s, min_profit_bps=%.1f, min_gap=%.1f cents)",
            self._enabled,
            self._min_profit_bps,
            self._cost_model.min_gap_cents(),
        )
        async for event in self._bus.subscribe():
            if event.get("topic") != "arb.spread":
                continue
            if not self._enabled:
                continue
            try:
                await self._handle_spread(event.get("data", {}))
            except Exception as exc:
                logger.error("ArbExecutor error: %s", exc, exc_info=True)

    async def _handle_spread(self, data: dict[str, Any]) -> None:
        """Process a spread observation and execute if profitable."""
        observation_id = data.get("observation_id") or data.get("id")
        gap_cents = data.get("gap_cents", 0)
        kalshi_ticker = data.get("kalshi_ticker", "")
        poly_ticker = data.get("poly_ticker", "")

        if not observation_id:
            return

        if not self._cost_model.should_execute(gap_cents, self._min_profit_bps):
            return

        # Skip if already trading this pair
        trade_key = f"{kalshi_ticker}:{poly_ticker}"
        if trade_key in self._active_trades:
            logger.debug("ArbExecutor: Skipping %s - trade already active", trade_key)
            return

        # Claim the spread
        claimed = await self._store.claim_spread(observation_id, "arb_executor")
        if not claimed:
            logger.debug("ArbExecutor: Failed to claim observation %s", observation_id)
            return

        logger.info(
            "ArbExecutor: Claimed spread %s (%s ↔ %s) gap=%.1f bps",
            observation_id,
            kalshi_ticker,
            poly_ticker,
            gap_cents,
        )

        # Build and execute trade
        self._active_trades[trade_key] = True
        try:
            success = await self._execute_arb(
                observation_id, kalshi_ticker, poly_ticker, gap_cents
            )
            if success:
                logger.info("ArbExecutor: Trade %s completed successfully", trade_key)
            else:
                logger.warning("ArbExecutor: Trade %s failed", trade_key)
        finally:
            self._active_trades.pop(trade_key, None)
            # Release the spread lock
            await self._store.release_spread(observation_id)

    async def _execute_arb(
        self,
        observation_id: int,
        kalshi_ticker: str,
        poly_ticker: str,
        gap_cents: float,
    ) -> bool:
        """Execute arbitrage via coordinator."""
        from execution.models import ArbTrade, ArbLeg, SequencingStrategy
        from broker.models import MarketOrder, OrderSide, Symbol, AssetType

        trade_id = f"arb-{uuid4().hex[:12]}"
        quantity = Decimal(
            str(self._max_position_usd / 100)
        )  # Simplified: $1 per contract

        # Determine sides based on pricing
        # If Kalshi > Polymarket: sell Kalshi, buy Polymarket
        # If Polymarket > Kalshi: buy Kalshi, sell Polymarket
        kalshi_side = OrderSide.SELL if gap_cents > 0 else OrderSide.BUY
        poly_side = OrderSide.BUY if gap_cents > 0 else OrderSide.SELL

        leg_a = ArbLeg(
            broker_id="kalshi",
            order=MarketOrder(
                symbol=Symbol(ticker=kalshi_ticker, asset_type=AssetType.STOCK),
                side=kalshi_side,
                quantity=quantity,
                account_id="default",
            ),
        )

        leg_b = ArbLeg(
            broker_id="polymarket",
            order=MarketOrder(
                symbol=Symbol(ticker=poly_ticker, asset_type=AssetType.STOCK),
                side=poly_side,
                quantity=quantity,
                account_id="default",
            ),
        )

        trade = ArbTrade(
            id=trade_id,
            symbol_a=kalshi_ticker,
            symbol_b=poly_ticker,
            leg_a=leg_a,
            leg_b=leg_b,
            expected_profit_bps=Decimal(str(abs(gap_cents))),
            sequencing=SequencingStrategy.CONCURRENT,
        )

        return await self._coordinator.execute_arbitrage(trade)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable auto-execution."""
        self._enabled = enabled
        logger.info(
            "ArbExecutor: Auto-execution %s", "ENABLED" if enabled else "DISABLED"
        )
