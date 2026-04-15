"""
Cross-Platform Arbitrage Agent.

Scans Kalshi and Polymarket, matches markets with EnhancedMatcher,
normalises contracts, records spread observations, and emits Opportunity
objects when the gap exceeds threshold_cents.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from agents.base import StructuredAgent
from agents.models import AgentConfig, Opportunity, OpportunityStatus
from broker.models import LimitOrder, Symbol, AssetType, OrderSide, TIF
from strategies.matching import match_markets
from strategies.normalization import normalize_contract, compute_confidence
from utils.ids import new_signal_id

logger = logging.getLogger(__name__)


class CrossPlatformArbAgent(StructuredAgent):
    description = "Cross-platform probability arbitrage between Kalshi and Polymarket."

    def __init__(
        self,
        config: AgentConfig,
        kalshi_ds=None,
        polymarket_ds=None,
        spread_store=None,
        event_bus=None,
        **kwargs,
    ):
        super().__init__(config, **kwargs)
        self.kalshi_ds = kalshi_ds
        self.polymarket_ds = polymarket_ds
        self.spread_store = spread_store
        # event_bus is optional. When provided, emit `arb.spread` events
        # alongside Opportunity objects so the ArbExecutor auto-execution
        # path (which currently only fires from the live WS/SpreadTracker
        # pipeline) can also fire from cron scans. Tests that don't pass
        # a bus stay green — no events published.
        self.event_bus = event_bus

        params = config.parameters or {}
        self.threshold = params.get("threshold_cents", 8)
        self.min_similarity = params.get("min_match_similarity", 0.35)
        # Gaps above this are almost always matcher error or inverse-direction
        # pairs that the current single-leg BUY execution can't trade correctly.
        # Spread observations are still recorded below; only the Opportunity
        # emission is gated. See docstring on scan() for the full rationale.
        self.max_gap_cents = params.get("max_gap_cents", 50)
        self.kalshi_categories = params.get(
            "kalshi_categories", ["economics", "politics", "climate"]
        )
        self.poly_tags = params.get(
            "polymarket_tags", ["politics", "crypto", "climate"]
        )
        self.max_markets = params.get("max_markets_per_platform", 50)
        self.alert_on_spread = params.get("alert_on_spread", True)

    async def scan(self, data) -> list[Opportunity]:
        if not self.kalshi_ds or not self.polymarket_ds:
            return []

        # Event-level matching — the `/markets` endpoints on both venues either
        # silently ignore the category/tag filter (Kalshi) or serve stale 2023
        # archive data (Polymarket CLOB). The `/events` endpoints are the
        # correct primitives (see commit 7c811da and the arb-pipeline memory).
        k_markets = await self.kalshi_ds.get_events(categories=self.kalshi_categories)
        p_markets = await self.polymarket_ds.get_events(tags=self.poly_tags)

        candidates = match_markets(k_markets, p_markets, min_score=self.min_similarity)

        logger.info(
            "cross_platform_arb.scan: kalshi=%d poly=%d candidates=%d "
            "(min_similarity=%.2f)",
            len(k_markets),
            len(p_markets),
            len(candidates),
            self.min_similarity,
        )

        k_lookup = {m.ticker: m for m in k_markets}
        p_lookup = {m.ticker: m for m in p_markets}

        opportunities = []
        now = datetime.now(timezone.utc)

        for cand in candidates:
            k_mkt = k_lookup.get(cand.kalshi_ticker)
            p_mkt = p_lookup.get(cand.poly_ticker)
            if not k_mkt or not p_mkt:
                continue

            k_norm = normalize_contract(k_mkt, platform="kalshi")
            p_norm = normalize_contract(p_mkt, platform="polymarket")

            # Prefer nested-market cached prices, fall back to live orderbook
            # when either side is None (Polymarket outcomePrices=[null,null] etc.)
            k_cents = k_mkt.yes_ask if k_mkt.yes_ask is not None else k_mkt.yes_bid
            p_cents = p_mkt.yes_bid

            if k_cents is None:
                ticker = k_mkt.native_market_id or cand.kalshi_ticker
                q = await self.kalshi_ds.get_quote(
                    Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)
                )
                if q is not None and q.ask is not None:
                    k_cents = int(q.ask * 100)
            if p_cents is None:
                ticker = p_mkt.native_market_id or cand.poly_ticker
                q = await self.polymarket_ds.get_quote(
                    Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)
                )
                if q is not None and q.bid is not None:
                    p_cents = int(q.bid * 100)

            # Dead-book filter: the orderbook fallback can reach the CLOB and
            # return a Decimal("0") bid (or an ask with no counter-bid) for
            # illiquid markets. Those aren't tradable — a 0¢ quote means
            # nobody is willing to buy/sell, not that the true price is 0.
            # Live 2026-04-15 probe: 4/4 null-cached events filled as bid=0.
            if k_cents is None or p_cents is None or k_cents <= 0 or p_cents <= 0:
                logger.debug(
                    "cross_platform_arb: skipping %s/%s — no tradable price "
                    "(k=%s p=%s; dead book or zero-depth orderbook)",
                    cand.kalshi_ticker,
                    cand.poly_ticker,
                    k_cents,
                    p_cents,
                )
                continue

            gap = abs(k_cents - p_cents)

            # Record spread observation for every matched pair (history building)
            # and capture the row id so we can reference it in the arb.spread
            # event published after opportunity emission (ArbExecutor uses
            # the id to claim the spread atomically via SpreadStore).
            observation_id: int | None = None
            if self.spread_store is not None:
                from storage.spreads import SpreadObservation

                obs = SpreadObservation(
                    kalshi_ticker=cand.kalshi_ticker,
                    poly_ticker=cand.poly_ticker,
                    match_score=cand.final_score,
                    kalshi_cents=k_cents,
                    poly_cents=p_cents,
                    gap_cents=gap,
                    kalshi_volume=k_norm.volume_usd_24h,
                    poly_volume=p_norm.volume_usd_24h,
                )
                observation_id = await self.spread_store.record(obs)

            if gap == 0 or gap <= self.threshold:
                continue

            # Quality guard: reject implausibly large gaps. These dominate
            # the signal at loose min_match_similarity values and are almost
            # always either matcher error (different questions) or inverse-
            # direction pairs that the single-leg BUY below cannot execute
            # as an arb. Spread observation above has already been recorded
            # for history, so this only gates emission.
            if gap > self.max_gap_cents:
                logger.debug(
                    "cross_platform_arb: skipping %s/%s — gap=%d¢ exceeds "
                    "max_gap_cents=%d (likely mismatch or inverse pair)",
                    cand.kalshi_ticker,
                    cand.poly_ticker,
                    gap,
                    self.max_gap_cents,
                )
                continue

            target_broker = "kalshi" if k_cents < p_cents else "polymarket"
            target_ticker = (
                cand.kalshi_ticker if target_broker == "kalshi" else cand.poly_ticker
            )
            target_account = "KALSHI" if target_broker == "kalshi" else "POLYMARKET"
            target_cents = min(k_cents, p_cents)
            limit_price = Decimal(str(target_cents)) / Decimal("100")

            sym = Symbol(ticker=target_ticker, asset_type=AssetType.PREDICTION)
            confidence = compute_confidence(gap_cents=gap, k_norm=k_norm, p_norm=p_norm)

            signal_id = new_signal_id()

            opportunities.append(
                Opportunity(
                    id=f"x_arb_{target_ticker}_{now.timestamp()}",
                    agent_name=self.name,
                    symbol=sym,
                    signal="BUY",
                    confidence=confidence,
                    reasoning=(
                        f"Kalshi: {k_cents}¢ | Polymarket: {p_cents}¢ | "
                        f"Gap: {gap}¢ | Target: {target_broker} | "
                        f"Match: {cand.final_score:.2f}\n"
                        f"Q: {k_mkt.title}"
                    ),
                    broker_id=target_broker,
                    suggested_trade=LimitOrder(
                        symbol=sym,
                        side=OrderSide.BUY,
                        quantity=Decimal("10"),
                        account_id=target_account,
                        limit_price=limit_price,
                        time_in_force=TIF.GTC,
                    ),
                    data={
                        "signal_id": signal_id,
                        "kalshi_ticker": cand.kalshi_ticker,
                        "poly_ticker": cand.poly_ticker,
                        "kalshi_cents": k_cents,
                        "polymarket_cents": p_cents,
                        "gap_cents": gap,
                        "target_broker": target_broker,
                        "match_score": cand.final_score,
                    },
                    timestamp=now,
                    status=OpportunityStatus.PENDING,
                )
            )

            # Feed the auto-execution path. ArbExecutor subscribes to
            # `arb.spread` and claims the observation id to build the
            # atomic 2-leg trade. Gated on event_bus + observation_id so
            # tests without a bus or without a spread_store stay quiet.
            # Execution remains gated by ArbExecutor.enabled (default
            # False) — this emission alone does not place orders.
            if self.event_bus is not None and observation_id is not None:
                try:
                    await self.event_bus.publish(
                        "arb.spread",
                        {
                            "signal_id": signal_id,
                            "observation_id": observation_id,
                            "kalshi_ticker": cand.kalshi_ticker,
                            "poly_ticker": cand.poly_ticker,
                            "kalshi_cents": k_cents,
                            "poly_cents": p_cents,
                            "gap_cents": gap,
                            "match_score": cand.final_score,
                            "observed_at": now.isoformat(),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "cross_platform_arb: event_bus.publish failed for "
                        "%s/%s (non-fatal): %s",
                        cand.kalshi_ticker,
                        cand.poly_ticker,
                        exc,
                    )

        opportunities.sort(key=lambda o: o.data["gap_cents"], reverse=True)
        return opportunities
