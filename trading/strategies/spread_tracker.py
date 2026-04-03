# python/strategies/spread_tracker.py
"""
SpreadTracker — subscribes to EventBus "polymarket.quote" events and records
spread observations for matched pairs. Publishes "arb.spread" events when
the gap exceeds alert_threshold_cents.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.events import EventBus
    from storage.spreads import SpreadStore
    from notifications.composite import CompositeNotifier

logger = logging.getLogger(__name__)


class SpreadTracker:
    """
    Listens to EventBus for polymarket.quote events and records spread
    observations for pairs that are already in the match index.
    """

    def __init__(
        self,
        spread_store: "SpreadStore",
        match_index: dict[str, str],      # poly_ticker (condition_id) -> kalshi_ticker
        event_bus: "EventBus",
        kalshi_ds,
        alert_threshold_cents: int = 8,
        notifier: "CompositeNotifier | None" = None,
    ) -> None:
        self._store = spread_store
        self._match_index = match_index    # mutable — updated by app.py on refresh
        self._bus = event_bus
        self._kalshi_ds = kalshi_ds
        self._threshold = alert_threshold_cents
        self._notifier = notifier

    async def run(self) -> None:
        async for event in self._bus.subscribe():
            if event["topic"] == "polymarket.quote":
                try:
                    await self._handle_quote(event["data"])
                except Exception as exc:
                    logger.warning("SpreadTracker._handle_quote error: %s", exc)

    async def _handle_quote(self, data: dict) -> None:
        condition_id: str = data.get("condition_id", "")
        kalshi_ticker = self._match_index.get(condition_id)
        if not kalshi_ticker:
            return

        poly_cents: int = data.get("yes_cents", 0)

        # Fetch current Kalshi price (the data source caches internally)
        k_mkt = await self._kalshi_ds.get_market(kalshi_ticker)
        if k_mkt is None:
            logger.warning("SpreadTracker: Kalshi market not found for ticker=%s", kalshi_ticker)
            return
        if k_mkt.yes_bid is None and k_mkt.yes_ask is None:
            return
        k_cents: int = k_mkt.yes_ask if k_mkt.yes_ask is not None else k_mkt.yes_bid
        gap = abs(k_cents - poly_cents)

        from storage.spreads import SpreadObservation
        obs = SpreadObservation(
            kalshi_ticker=kalshi_ticker,
            poly_ticker=condition_id,
            match_score=0.0,   # match_score not available here; set to 0
            kalshi_cents=k_cents,
            poly_cents=poly_cents,
            gap_cents=gap,
            kalshi_volume=float(k_mkt.volume_24h),
            poly_volume=0.0,
        )
        await self._store.record(obs)

        if gap > self._threshold:
            await self._bus.publish("arb.spread", {
                "kalshi_ticker": kalshi_ticker,
                "poly_ticker": condition_id,
                "kalshi_cents": k_cents,
                "poly_cents": poly_cents,
                "gap_cents": gap,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            })
            if self._notifier:
                try:
                    await self._notifier.notify(
                        f"Arb spread alert: {kalshi_ticker} vs {condition_id} — gap {gap}¢"
                    )
                except Exception as exc:
                    logger.warning("SpreadTracker notifier failed: %s", exc)
