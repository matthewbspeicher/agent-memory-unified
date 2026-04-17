"""ArbExecutor — auto-executes arbitrage when spreads exceed threshold."""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from execution.cost_model import CostModel
from agents.models import TrustLevel
from utils.logging import log_event

if TYPE_CHECKING:
    from data.events import EventBus
    from storage.spreads import SpreadStore
    from execution.arbitrage import ArbCoordinator
    from broker.models import Symbol
    from sizing.engine import SizingEngine

logger = logging.getLogger(__name__)


class ArbExecutor:
    """Subscribes to arb.spread events and auto-executes profitable opportunities.

    Paper-routing safety: when `paper_route=True` (default), every outgoing
    leg has its broker_id rewritten from "kalshi"/"polymarket" to
    "kalshi_paper"/"polymarket_paper" before the coordinator sees it.
    This keeps the live market-data clients (needed for the matching
    universe — the demo Kalshi has different tickers) while routing fills
    through in-process paper brokers. Setting `paper_route=False` sends
    real orders; only do so after explicit operator review.

    If paper_route=True but the coordinator's broker map does not contain
    the *_paper entries, the executor refuses to execute and logs a loud
    error. Fail-closed: never silently fall through to a live broker.
    """

    def __init__(
        self,
        spread_store: SpreadStore,
        arb_coordinator: ArbCoordinator,
        event_bus: EventBus,
        cost_model: CostModel | None = None,
        min_profit_bps: float = 5.0,
        max_position_usd: float = 100.0,
        enabled: bool = False,
        paper_route: bool = True,
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
        self._paper_route = paper_route
        # First-miss log flag for the per-event paper-broker availability
        # check. Prevents log spam if paper brokers never get wired.
        self._paper_missing_logged = False
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

    def _resolve_broker_id(self, venue: str) -> str:
        """Apply paper-route translation to a venue name.

        In paper_route mode: kalshi -> kalshi_paper, polymarket -> polymarket_paper.
        In live-route mode: passthrough. Used by _execute_arb when building
        ArbLeg objects so the translation happens exactly once, at the
        executor boundary, and is auditable from the leg's broker_id.
        """
        if not self._paper_route:
            return venue
        return f"{venue}_paper"

    def _paper_brokers_available(self) -> bool:
        """Verify the paper brokers exist in the coordinator's broker map
        before placing a trade. Fail-closed: if either is missing, we
        refuse to route. Prevents the coordinator from silently dropping
        a kalshi_paper leg while happily placing the polymarket leg
        (broken arb that loses the cross-venue hedge)."""
        brokers = getattr(self._coordinator, "_brokers", {}) or {}
        return "kalshi_paper" in brokers and "polymarket_paper" in brokers

    async def run(self) -> None:
        """Subscribe to spread events and execute when profitable."""
        logger.info(
            "ArbExecutor: Starting (enabled=%s, paper_route=%s, min_profit_bps=%.1f, min_gap=%.1f cents)",
            self._enabled,
            self._paper_route,
            self._min_profit_bps,
            self._cost_model.min_gap_cents(),
        )
        if self._enabled and not self._paper_route:
            # Live routing — loud startup warning so the operator who
            # flipped STA_ARB_ROUTE_LIVE=true sees it in logs.
            logger.warning(
                "⚠️  ArbExecutor: LIVE routing active — real orders will be placed. "
                "kalshi_demo=%s, polymarket_dry_run=%s. Max position per leg: $%.2f.",
                os.getenv("STA_KALSHI_DEMO", "<unset>"),
                os.getenv("STA_POLYMARKET_DRY_RUN", "<unset>"),
                self._max_position_usd,
            )
        async for event in self._bus.subscribe():
            if event.get("topic") != "arb.spread":
                continue
            # Per-event paper-broker check. Was previously done once at
            # startup, but app.py wires the paper brokers into the
            # coordinator's broker map AFTER spawning the executor task —
            # there's a ~25s window where kalshi_paper isn't in the map
            # yet. Checking per-event lets the executor safely shadow
            # during that window and start executing once the paper
            # brokers arrive. Fail-closed posture is preserved: the
            # default route if the brokers never appear is shadow, not
            # live. The first-miss log is loud so an operator who left
            # paper_trading=False notices.
            if self._enabled and self._paper_route and not self._paper_brokers_available():
                if not self._paper_missing_logged:
                    logger.error(
                        "ArbExecutor: paper_route=True but kalshi_paper / "
                        "polymarket_paper brokers not in coordinator broker "
                        "map yet. Running as shadow until they are wired. "
                        "If this message persists past startup, check "
                        "config.paper_trading and setup_paper_brokers."
                    )
                    self._paper_missing_logged = True
                await self._log_shadow_decision(event.get("data", {}))
                continue
            if not self._enabled:
                await self._log_shadow_decision(event.get("data", {}))
                continue
            try:
                await self._handle_spread(event.get("data", {}))
            except Exception as exc:
                logger.error("ArbExecutor error: %s", exc, exc_info=True)

    async def _handle_spread(self, data: dict[str, Any]) -> None:
        """Process a spread observation and execute if profitable."""
        observation_id = data.get("observation_id") or data.get("id")
        signal_id = data.get("signal_id")
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
                signal_id=signal_id,
            )
            if success:
                logger.info("ArbExecutor: Trade %s completed successfully", trade_key)
            else:
                logger.warning("ArbExecutor: Trade %s failed", trade_key)
        finally:
            self._active_trades.pop(trade_key, None)
            # Release the spread lock
            await self._store.release_spread(observation_id)

    async def _log_shadow_decision(self, data: dict[str, Any]) -> None:
        """When disabled, run the same gates as _handle_spread but only log —
        never claim the spread or dispatch to the coordinator."""
        observation_id = data.get("observation_id") or data.get("id")
        signal_id = data.get("signal_id")
        gap_cents = data.get("gap_cents", 0)
        kalshi_ticker = data.get("kalshi_ticker", "")
        poly_ticker = data.get("poly_ticker", "")
        kalshi_cents = data.get("kalshi_cents")
        poly_cents = data.get("poly_cents")

        if not observation_id:
            return

        would_execute = True
        reason_blocked: str | None = None

        if not self._cost_model.should_execute(gap_cents, self._min_profit_bps):
            would_execute = False
            reason_blocked = "below_min_profit_bps"

        computed_quantity = await self._compute_quantity(kalshi_cents, poly_cents)

        kalshi_side = "SELL" if gap_cents > 0 else "BUY"
        poly_side = "BUY" if gap_cents > 0 else "SELL"

        log_event(
            logger,
            logging.INFO,
            "arb.shadow",
            f"Shadow: {kalshi_ticker} ↔ {poly_ticker} gap={gap_cents} would_execute={would_execute}",
            data={
                "observation_id": observation_id,
                "signal_id": signal_id,
                "tickers": f"{kalshi_ticker} ↔ {poly_ticker}",
                "gap_cents": gap_cents,
                "prices": {"kalshi_cents": kalshi_cents, "poly_cents": poly_cents},
                "would_execute": would_execute,
                "reason_blocked": reason_blocked,
                "kalshi_side": kalshi_side,
                "poly_side": poly_side,
                "computed_quantity": str(computed_quantity),
            },
        )

    async def _execute_arb(
        self,
        observation_id: int,
        kalshi_ticker: str,
        poly_ticker: str,
        gap_cents: float,
        kalshi_cents: int | None = None,
        poly_cents: int | None = None,
        signal_id: str | None = None,
    ) -> bool:
        """Execute arbitrage via coordinator."""
        from execution.models import ArbTrade, ArbLeg, SequencingStrategy
        from broker.models import LimitOrder, MarketOrder, OrderSide, Symbol, AssetType

        trade_id = f"arb-{uuid4().hex[:12]}"
        quantity = await self._compute_quantity(kalshi_cents, poly_cents)

        # Determine sides based on pricing
        # If Kalshi > Polymarket: sell Kalshi, buy Polymarket
        # If Polymarket > Kalshi: buy Kalshi, sell Polymarket
        kalshi_side = OrderSide.SELL if gap_cents > 0 else OrderSide.BUY
        poly_side = OrderSide.BUY if gap_cents > 0 else OrderSide.SELL

        # Order type depends on routing. Paper brokers (KalshiPaperBroker,
        # PolymarketPaperBroker) only accept LimitOrder — they need an
        # explicit price to synthesize a fill. Live routing keeps
        # MarketOrder so we take the best available price at submission.
        # Observed spread prices come from the scan (kalshi_cents /
        # poly_cents) and are in 0–99¢ space; we divide by 100 to land in
        # the Decimal dollars the LimitOrder expects.
        def _build_order(ticker: str, side: OrderSide, cents: int | None):
            sym = Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)
            if self._paper_route:
                # Fall back to 50¢ if the observation didn't carry a
                # price. This is defensive — real paths always have cents.
                price = Decimal(str((cents or 50) / 100.0))
                return LimitOrder(
                    symbol=sym,
                    side=side,
                    quantity=quantity,
                    limit_price=price,
                    account_id="default",
                    signal_id=signal_id,
                )
            return MarketOrder(
                symbol=sym,
                side=side,
                quantity=quantity,
                account_id="default",
                signal_id=signal_id,
            )

        # Paper-route translation happens here, at the executor boundary.
        # _resolve_broker_id("kalshi") → "kalshi_paper" when self._paper_route,
        # "kalshi" when self._paper_route is False. The leg's broker_id is
        # what the ArbCoordinator routes by, so translating once at leg
        # construction guarantees the downstream coordinator + broker
        # clients never see a mixed/ambiguous routing state.
        leg_a = ArbLeg(
            broker_id=self._resolve_broker_id("kalshi"),
            order=_build_order(kalshi_ticker, kalshi_side, kalshi_cents),
        )

        leg_b = ArbLeg(
            broker_id=self._resolve_broker_id("polymarket"),
            order=_build_order(poly_ticker, poly_side, poly_cents),
        )

        trade = ArbTrade(
            id=trade_id,
            symbol_a=kalshi_ticker,
            symbol_b=poly_ticker,
            leg_a=leg_a,
            leg_b=leg_b,
            expected_profit_bps=Decimal(str(abs(gap_cents))),
            signal_id=signal_id,
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
