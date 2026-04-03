"""ResolutionTracker — background task that auto-settles resolved paper positions."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.kalshi.client import KalshiClient
    from adapters.kalshi.paper import KalshiPaperBroker
    from adapters.polymarket.client import PolymarketClient
    from adapters.polymarket.paper import PolymarketPaperBroker
    from data.events import EventBus
    from storage.paper import PaperStore

logger = logging.getLogger(__name__)


class ResolutionTracker:
    """
    Background task that polls Kalshi and Polymarket for resolved markets
    and auto-settles matching open paper positions.

    Architecture:
      - Runs as an asyncio.Task started during app lifespan.
      - Polls on a configurable interval (default: 10 minutes).
      - For each open paper position, checks if the market has resolved.
      - Calls broker.resolve_contract() on the paper broker for resolved markets.
      - Emits an event via EventBus so the dashboard and notifier can react.
      - record_binary_resolution() is idempotent, so duplicate polls are safe.
    """

    def __init__(
        self,
        kalshi_client: "KalshiClient | None",
        polymarket_client: "PolymarketClient | None",
        kalshi_paper_broker: "KalshiPaperBroker | None",
        polymarket_paper_broker: "PolymarketPaperBroker | None",
        paper_store: "PaperStore",
        event_bus: "EventBus | None" = None,
        poll_interval_seconds: int = 600,
    ) -> None:
        self._kalshi_client = kalshi_client
        self._poly_client = polymarket_client
        self._kalshi_paper = kalshi_paper_broker
        self._poly_paper = polymarket_paper_broker
        self._paper_store = paper_store
        self._event_bus = event_bus
        self._poll_interval = poll_interval_seconds

    async def run(self) -> None:
        """Main loop. Call via asyncio.create_task(tracker.run())."""
        while True:
            try:
                await self._check_resolutions()
            except Exception as exc:
                logger.warning("ResolutionTracker poll failed: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _check_resolutions(self) -> None:
        if self._kalshi_paper and self._kalshi_client:
            await self._settle_kalshi()
        if self._poly_paper and self._poly_client:
            await self._settle_polymarket()

    async def _settle_kalshi(self) -> None:
        from adapters.kalshi.paper import KALSHI_PAPER_ACCOUNT_ID
        positions = await self._paper_store.get_positions(KALSHI_PAPER_ACCOUNT_ID)
        for pos in positions:
            try:
                market = await self._kalshi_client.get_market(pos.symbol.ticker)
            except Exception as exc:
                logger.warning("Kalshi get_market failed for %s: %s", pos.symbol.ticker, exc)
                continue
            status = market.get("status", "")
            result = market.get("result", "")
            if status == "finalized" and result in ("yes", "no", "void"):
                resolution = "CANCELLED" if result == "void" else result.upper()
                await self._kalshi_paper.resolve_contract(
                    account_id=KALSHI_PAPER_ACCOUNT_ID,
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    entry_price=pos.avg_cost,
                    resolution=resolution,
                )
                logger.info(
                    "ResolutionTracker: settled Kalshi %s → %s",
                    pos.symbol.ticker, resolution,
                )
                if self._event_bus:
                    await self._event_bus.publish("market_resolved", {
                        "broker": "kalshi",
                        "ticker": pos.symbol.ticker,
                        "resolution": resolution,
                    })

    async def _settle_polymarket(self) -> None:
        from adapters.polymarket.paper import POLYMARKET_PAPER_ACCOUNT_ID
        positions = await self._paper_store.get_positions(POLYMARKET_PAPER_ACCOUNT_ID)
        for pos in positions:
            try:
                market = await asyncio.to_thread(self._poly_client.get_market, pos.symbol.ticker)
            except Exception as exc:
                logger.warning("Polymarket get_market failed for %s: %s", pos.symbol.ticker, exc)
                continue
            if market.get("closed") and market.get("resolved"):
                winning_tokens = market.get("winning_outcomes", [])
                if not winning_tokens:
                    logger.warning(
                        "ResolutionTracker: market %s is resolved but winning_outcomes is empty",
                        pos.symbol.ticker,
                    )
                resolution = "YES" if pos.symbol.ticker in winning_tokens else "NO"
                await self._poly_paper.resolve_contract(
                    account_id=POLYMARKET_PAPER_ACCOUNT_ID,
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    entry_price=pos.avg_cost,
                    resolution=resolution,
                )
                logger.info(
                    "ResolutionTracker: settled Polymarket %s → %s",
                    pos.symbol.ticker, resolution,
                )
                if self._event_bus:
                    await self._event_bus.publish("market_resolved", {
                        "broker": "polymarket",
                        "ticker": pos.symbol.ticker,
                        "resolution": resolution,
                    })
