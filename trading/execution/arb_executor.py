"""ArbExecutor — auto-executes arbitrage when spreads exceed threshold."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from execution.cost_model import CostModel
from agents.models import TrustLevel

if TYPE_CHECKING:
    from data.events import EventBus
    from storage.spreads import SpreadStore
    from execution.arbitrage import ArbCoordinator
    from broker.models import Symbol
    from sizing.engine import SizingEngine

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
        sizing_engine: SizingEngine | None = None,
        bankroll_usd: Decimal | float = Decimal("100"),
        agent_name: str = "cross_platform_arb",
        trust_level: TrustLevel = TrustLevel.MONITORED,
    ) -> None:
        self._store = spread_store
        self._coordinator = arb_coordinator
        self._bus = event_bus
        self._cost_model = cost_model or CostModel()
        self._min_profit_bps = min_profit_bps
        self._max_position_usd = max_position_usd
        self._enabled = enabled
        self._active_trades: dict[str, bool] = {}
        # Sizing — when SizingEngine is provided, use Kelly + trust scaling;
        # otherwise fall back to the minimum-size floor (Decimal("1")), which
        # is what the engine itself returns when there's insufficient
        # performance data. This preserves existing test behaviour for sites
        # that construct ArbExecutor without passing a sizing engine.
        self._sizing_engine = sizing_engine
        self._bankroll_usd = Decimal(str(bankroll_usd))
        self._agent_name = agent_name
        self._trust_level = trust_level

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
        kalshi_cents = data.get("kalshi_cents")
        poly_cents = data.get("poly_cents")

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
                observation_id,
                kalshi_ticker,
                poly_ticker,
                gap_cents,
                kalshi_cents=kalshi_cents,
                poly_cents=poly_cents,
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
        kalshi_cents: int | None = None,
        poly_cents: int | None = None,
    ) -> bool:
        """Execute arbitrage via coordinator."""
        from execution.models import ArbTrade, ArbLeg, SequencingStrategy
        from broker.models import MarketOrder, OrderSide, Symbol, AssetType

        trade_id = f"arb-{uuid4().hex[:12]}"
        quantity = await self._compute_quantity(kalshi_cents, poly_cents)

        # Determine sides based on pricing
        # If Kalshi > Polymarket: sell Kalshi, buy Polymarket
        # If Polymarket > Kalshi: buy Kalshi, sell Polymarket
        kalshi_side = OrderSide.SELL if gap_cents > 0 else OrderSide.BUY
        poly_side = OrderSide.BUY if gap_cents > 0 else OrderSide.SELL

        leg_a = ArbLeg(
            broker_id="kalshi",
            order=MarketOrder(
                symbol=Symbol(ticker=kalshi_ticker, asset_type=AssetType.PREDICTION),
                side=kalshi_side,
                quantity=quantity,
                account_id="default",
            ),
        )

        leg_b = ArbLeg(
            broker_id="polymarket",
            order=MarketOrder(
                symbol=Symbol(ticker=poly_ticker, asset_type=AssetType.PREDICTION),
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
            sequencing=SequencingStrategy.LESS_LIQUID_FIRST,
        )

        return await self._coordinator.execute_arbitrage(trade)

    async def _compute_quantity(
        self,
        kalshi_cents: int | None,
        poly_cents: int | None,
    ) -> Decimal:
        """Compute order quantity using SizingEngine when configured.

        When no SizingEngine is wired (test construction, legacy paths) or
        when performance history is insufficient, SizingEngine itself
        returns Decimal("1") — we preserve that floor here as the fallback
        so that behaviour is identical whether or not the engine is present.
        """
        if self._sizing_engine is None:
            return Decimal("1")

        # Reference price for Kelly sizing: midpoint of the two venues, in
        # dollars. If either leg's price is unknown (defensive default),
        # fall back to 50¢ — neutral prediction-market price — which yields
        # a reasonable Kelly size without blowing up on missing data.
        if kalshi_cents is not None and poly_cents is not None:
            mid_cents = (kalshi_cents + poly_cents) / 2.0
        else:
            mid_cents = 50.0
        price = Decimal(str(mid_cents / 100.0))

        try:
            qty = await self._sizing_engine.compute_size(
                agent_name=self._agent_name,
                trust_level=self._trust_level,
                price=price,
                bankroll=self._bankroll_usd,
            )
            return max(qty, Decimal("1"))
        except Exception as exc:  # defensive — sizing must never block exec
            logger.warning(
                "ArbExecutor sizing failed (%s); falling back to 1 share", exc
            )
            return Decimal("1")

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable auto-execution."""
        self._enabled = enabled
        logger.info(
            "ArbExecutor: Auto-execution %s", "ENABLED" if enabled else "DISABLED"
        )

    def set_sizing_engine(self, sizing_engine: SizingEngine | None) -> None:
        """Inject the SizingEngine after construction.

        Used by app.py lifespan where ArbExecutor is built before the
        SizingEngine (the engine depends on perf_store which is wired
        later). When None, _compute_quantity falls back to Decimal("1").
        """
        self._sizing_engine = sizing_engine
        logger.info(
            "ArbExecutor: SizingEngine %s",
            "wired" if sizing_engine is not None else "cleared",
        )
