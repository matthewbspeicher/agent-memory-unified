from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch


async def test_connect_authenticates():
    from adapters.alpaca.stream import AlpacaStream

    stream = AlpacaStream(api_key="test_key", secret_key="test_secret", data_feed="iex")

    mock_ws = MagicMock()
    mock_ws.recv = AsyncMock(return_value='[{"T":"success","msg":"authenticated"}]')
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()

    mock_connect = AsyncMock(return_value=mock_ws)

    with patch("adapters.alpaca.stream.websockets.connect", mock_connect):
        await stream.connect()

    assert stream.is_connected()
    mock_ws.send.assert_called()  # auth message sent


async def test_subscribe_stores_symbols():
    from adapters.alpaca.stream import AlpacaStream

    stream = AlpacaStream(api_key="test", secret_key="test")
    stream._ws = AsyncMock()
    stream._ws.send = AsyncMock()
    stream._connected = True

    await stream.subscribe(["AAPL", "TSLA"])

    assert "AAPL" in stream._subscribed_symbols
    assert "TSLA" in stream._subscribed_symbols


async def test_reconnect_replays_subscriptions():
    from adapters.alpaca.stream import AlpacaStream

    stream = AlpacaStream(api_key="test", secret_key="test")
    stream._subscribed_symbols = {"AAPL", "TSLA"}
    stream.connect = AsyncMock()
    stream.subscribe = AsyncMock()

    await stream.reconnect()

    stream.connect.assert_called_once()
    stream.subscribe.assert_called_once()
    call_args = stream.subscribe.call_args[0][0]
    assert set(call_args) == {"AAPL", "TSLA"}
