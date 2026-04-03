from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_sandbox_url():
    from adapters.tradier.stream import TradierStream
    stream = TradierStream(token="test", sandbox=True)
    assert "sandbox" in stream._base_url


def test_live_url():
    from adapters.tradier.stream import TradierStream
    stream = TradierStream(token="test", sandbox=False)
    assert "sandbox" not in stream._base_url


async def test_subscribe_stores_symbols():
    from adapters.tradier.stream import TradierStream
    stream = TradierStream(token="test", sandbox=True)
    stream._connected = True
    stream._session_url = "https://mock-stream-url"
    stream._sse_task = MagicMock()

    # Mock the internal reconnect that subscribe triggers
    stream._restart_sse = AsyncMock()

    await stream.subscribe(["AAPL", "TSLA"])

    assert "AAPL" in stream._subscribed_symbols
    assert "TSLA" in stream._subscribed_symbols


async def test_reconnect_replays_subscriptions():
    from adapters.tradier.stream import TradierStream
    stream = TradierStream(token="test", sandbox=True)
    stream._subscribed_symbols = {"AAPL"}
    stream.connect = AsyncMock()
    stream.subscribe = AsyncMock()

    await stream.reconnect()

    stream.connect.assert_called_once()
    stream.subscribe.assert_called_once_with(["AAPL"])
