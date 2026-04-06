from __future__ import annotations
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock


from broker.models import Quote, Symbol


async def test_subscribe_deduplicates():
    from streaming.manager import StreamManager

    stream_a = MagicMock()
    stream_a.subscribe = AsyncMock()
    stream_a.on_quote = MagicMock()

    stream_b = MagicMock()
    stream_b.subscribe = AsyncMock()
    stream_b.on_quote = MagicMock()

    mgr = StreamManager(
        streams={"alpaca": stream_a, "tradier": stream_b},
        data_bus=MagicMock(),
        event_bus=MagicMock(),
    )

    await mgr.subscribe(["AAPL"], broker="alpaca")
    await mgr.subscribe(["AAPL"], broker="tradier")  # should be skipped (dedup)

    stream_a.subscribe.assert_called_once_with(["AAPL"])
    stream_b.subscribe.assert_not_called()


async def test_fan_out_updates_databus_and_eventbus():
    from streaming.manager import StreamManager

    mock_data_bus = MagicMock()
    mock_data_bus.update_quote_cache = AsyncMock()
    mock_event_bus = MagicMock()
    mock_event_bus.publish = AsyncMock()

    mgr = StreamManager(
        streams={},
        data_bus=mock_data_bus,
        event_bus=mock_event_bus,
    )

    quote = Quote(
        symbol=Symbol(ticker="AAPL"), bid=Decimal("150.0"), ask=Decimal("150.5")
    )
    await mgr._on_quote("AAPL", quote)

    mock_data_bus.update_quote_cache.assert_called_once()
    mock_event_bus.publish.assert_called_once_with("quote.AAPL", quote)


async def test_invalidate_on_disconnect():
    from streaming.manager import StreamManager

    mock_data_bus = MagicMock()
    mock_data_bus.invalidate_quote_cache = MagicMock()

    mgr = StreamManager(
        streams={},
        data_bus=mock_data_bus,
        event_bus=MagicMock(),
    )
    mgr._symbol_to_broker = {"AAPL": "alpaca", "TSLA": "alpaca", "MSFT": "tradier"}

    mgr._on_stream_disconnected("alpaca")

    mock_data_bus.invalidate_quote_cache.assert_called_once_with(["AAPL", "TSLA"])
