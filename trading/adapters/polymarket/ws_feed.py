"""
PolymarketWebSocketFeed — long-running task that subscribes to the Polymarket
CLOB WebSocket and publishes price_change events to the EventBus.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.polymarket.data_source import PolymarketDataSource
    from data.events import EventBus

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
_RECONNECT_BASE = 1
_RECONNECT_MAX = 30


class PolymarketWebSocketFeed:
    """
    Connects to the Polymarket CLOB WebSocket, subscribes to price_change
    events for all active token IDs, and writes live prices into
    data_source._live_price_cache (condition_id → yes_cents).

    Publishes EventBus topic "polymarket.quote" on every price update.
    Reconnects with exponential backoff on disconnect.
    """

    def __init__(
        self,
        data_source: "PolymarketDataSource",
        event_bus: "EventBus",
    ) -> None:
        self._ds = data_source
        self._bus = event_bus

    async def run(self, token_ids: list[str]) -> None:
        """Connect, subscribe, read messages, reconnect on drop."""
        delay = _RECONNECT_BASE
        failures = 0
        while True:
            try:
                import websockets  # type: ignore[import]
                async with websockets.connect(WS_URL) as ws:
                    delay = _RECONNECT_BASE  # reset on successful connect
                    failures = 0
                    await self._subscribe(ws, token_ids)
                    logger.info(
                        "PolymarketWebSocketFeed: connected, subscribed to %d tokens",
                        len(token_ids),
                    )
                    async for raw in ws:
                        await self._handle_message(raw)
            except Exception as exc:
                failures += 1
                # Log first 3 failures as WARNING, then switch to DEBUG to reduce noise
                if failures <= 3:
                    logger.warning(
                        "PolymarketWebSocketFeed: disconnected (%s), retrying in %ds", exc, delay
                    )
                elif failures == 4:
                    logger.warning(
                        "PolymarketWebSocketFeed: repeated failures (%d), "
                        "suppressing further warnings (DNS unreachable?)", failures
                    )
                else:
                    logger.debug(
                        "PolymarketWebSocketFeed: disconnected (%s), retrying in %ds", exc, delay
                    )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _RECONNECT_MAX)

    async def _subscribe(self, ws, token_ids: list[str]) -> None:
        """Send subscribe message per CLOB WebSocket protocol."""
        payload = json.dumps({
            "auth": None,
            "type": "Market",
            "assets_ids": token_ids,
        })
        await ws.send(payload)

    async def _handle_message(self, raw: str) -> None:
        """Parse a WebSocket message, update price cache, publish to EventBus."""
        try:
            events = json.loads(raw)
            if not isinstance(events, list):
                return
            for evt in events:
                if evt.get("event_type") != "price_change":
                    continue
                condition_id: str = evt.get("asset_id", "")
                price_str: str = str(evt.get("price", "0"))
                try:
                    yes_cents = int(float(price_str) * 100)
                except (ValueError, TypeError):
                    continue
                if not condition_id:
                    continue
                
                # Update live price cache on the data source
                await self._ds._live_price_cache.update(condition_id, yes_cents)
                
                # Publish to EventBus
                publish_coro = self._bus.publish(
                    "polymarket.quote",
                    {
                        "condition_id": condition_id,
                        "yes_cents": yes_cents,
                    },
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(publish_coro)
                except RuntimeError:
                    # No running loop — log at debug and skip publish (non-fatal)
                    logger.debug("PolymarketWebSocketFeed: no running loop, skipping publish")
        except Exception as exc:
            logger.warning("PolymarketWebSocketFeed._handle_message error: %s", exc)
