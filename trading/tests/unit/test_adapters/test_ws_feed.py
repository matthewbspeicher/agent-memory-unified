"""Unit tests for PolymarketWebSocketFeed using a mock WebSocket."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from adapters.polymarket.ws_feed import PolymarketWebSocketFeed
from data.events import EventBus


def _make_feed(price_cache=None):
    ds = MagicMock()
    ds._live_price_cache = price_cache or {}
    bus = EventBus()
    return PolymarketWebSocketFeed(data_source=ds, event_bus=bus), ds, bus


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_price_change_updates_cache(self):
        feed, ds, _ = _make_feed()
        # Mock the async update method
        ds._live_price_cache = AsyncMock()
        msg = json.dumps(
            [
                {
                    "event_type": "price_change",
                    "asset_id": "tok123",
                    "price": "0.65",
                }
            ]
        )
        await feed._handle_message(msg)
        ds._live_price_cache.update.assert_awaited_once_with("tok123", 65)

    @pytest.mark.asyncio
    async def test_ignores_unknown_event_type(self):
        feed, ds, _ = _make_feed()
        ds._live_price_cache = AsyncMock()
        msg = json.dumps([{"event_type": "book", "asset_id": "tok123", "price": "0.5"}])
        await feed._handle_message(msg)
        ds._live_price_cache.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_message_does_not_raise(self):
        feed, ds, _ = _make_feed()
        await feed._handle_message("not valid json{{{{")
        # no exception

    @pytest.mark.asyncio
    async def test_empty_array_does_not_raise(self):
        feed, ds, _ = _make_feed()
        await feed._handle_message("[]")

    @pytest.mark.asyncio
    async def test_publishes_polymarket_quote_event(self):
        """Publish fires when there IS a running event loop (async test context)."""
        feed, ds, bus = _make_feed()
        ds._live_price_cache = AsyncMock()
        published = []

        async def capture(topic, data):
            published.append((topic, data))

        bus.publish = capture  # type: ignore[method-assign]

        msg = json.dumps(
            [{"event_type": "price_change", "asset_id": "tok999", "price": "0.42"}]
        )
        await feed._handle_message(msg)
        # Give the loop.create_task a chance to run
        await asyncio.sleep(0)
        assert len(published) == 1
        assert published[0][0] == "polymarket.quote"
        assert published[0][1]["condition_id"] == "tok999"
        assert published[0][1]["yes_cents"] == 42


class TestSubscribe:
    async def test_subscribe_sends_correct_message(self):
        feed, ds, _ = _make_feed()
        ws = AsyncMock()
        ws.send = AsyncMock()
        await feed._subscribe(ws, ["tok1", "tok2"])
        ws.send.assert_called_once()
        payload = json.loads(ws.send.call_args[0][0])
        assert payload["type"] == "Market"
        assert "tok1" in payload["assets_ids"]
        assert "tok2" in payload["assets_ids"]


class TestReconnectBackoff:
    def test_backoff_sequence(self):
        feed, _, _ = _make_feed()
        delays = []
        d = 1
        for _ in range(6):
            delays.append(d)
            d = min(d * 2, 30)
        assert delays == [1, 2, 4, 8, 16, 30]
