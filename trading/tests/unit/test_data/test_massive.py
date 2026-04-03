"""Tests for MassiveClient and MassiveDataSource."""
from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data.massive import MassiveClient
from data.massive_source import MassiveDataSource
from broker.models import Symbol


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


def _make_client_mock(json_data: dict) -> MagicMock:
    """Return an AsyncMock httpx.AsyncClient that returns *json_data* on .get()."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=_mock_response(json_data))
    return mock


# ---------------------------------------------------------------------------
# MassiveClient — initialisation
# ---------------------------------------------------------------------------

def test_init_stores_api_key():
    c = MassiveClient(api_key="test-key")
    assert c._key == "test-key"


def test_base_url_is_massive():
    assert MassiveClient.BASE_URL == "https://api.massive.com"


def test_params_appends_api_key():
    c = MassiveClient(api_key="abc123")
    p = c._params()
    assert p["apiKey"] == "abc123"


def test_params_merges_extra():
    c = MassiveClient(api_key="abc123")
    p = c._params({"limit": 100, "adjusted": "true"})
    assert p["apiKey"] == "abc123"
    assert p["limit"] == 100
    assert p["adjusted"] == "true"


# ---------------------------------------------------------------------------
# MassiveClient — get_bars
# ---------------------------------------------------------------------------

_BARS_PAYLOAD = {
    "results": [
        {"t": 1704067200000, "o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 1_000_000},
        {"t": 1704153600000, "o": 186.5, "h": 188.0, "l": 185.5, "c": 187.0, "v": 900_000},
    ],
    "status": "OK",
}


@pytest.mark.asyncio
async def test_get_bars_returns_results_list():
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(_BARS_PAYLOAD)

    bars = await c.get_bars("AAPL", 1, "day", "2024-01-01", "2024-01-02")

    assert len(bars) == 2
    assert bars[0]["t"] == 1704067200000


@pytest.mark.asyncio
async def test_get_bars_calls_correct_url():
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(_BARS_PAYLOAD)

    await c.get_bars("AAPL", 1, "day", "2024-01-01", "2024-01-02")

    call_kwargs = c._client.get.call_args
    url: str = call_kwargs[0][0]
    assert "/v2/aggs/ticker/AAPL/range/1/day/2024-01-01/2024-01-02" in url


@pytest.mark.asyncio
async def test_get_bars_includes_api_key_in_params():
    c = MassiveClient(api_key="secret-key")
    c._client = _make_client_mock(_BARS_PAYLOAD)

    await c.get_bars("AAPL", 1, "day", "2024-01-01", "2024-01-02")

    params = c._client.get.call_args[1]["params"]
    assert params["apiKey"] == "secret-key"


@pytest.mark.asyncio
async def test_get_bars_handles_pagination():
    """Verify that next_url pages are fetched and results concatenated."""
    page1 = {
        "results": [{"t": 1704067200000, "o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 100}],
        "next_url": "https://api.massive.com/v2/aggs/ticker/AAPL/range/1/day/...?cursor=abc",
        "status": "OK",
    }
    page2 = {
        "results": [{"t": 1704153600000, "o": 186.5, "h": 188.0, "l": 185.5, "c": 187.0, "v": 200}],
        "status": "OK",
    }

    c = MassiveClient(api_key="k")
    responses = [_mock_response(page1), _mock_response(page2)]
    c._client = AsyncMock()
    c._client.get = AsyncMock(side_effect=responses)

    bars = await c.get_bars("AAPL", 1, "day", "2024-01-01", "2024-01-02")

    assert len(bars) == 2
    # Second call should go to the next_url
    second_call_url = c._client.get.call_args_list[1][0][0]
    assert "cursor=abc" in second_call_url


@pytest.mark.asyncio
async def test_get_bars_pagination_adds_api_key_to_next_page():
    page1 = {
        "results": [{"t": 1704067200000, "o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 100}],
        "next_url": "https://api.massive.com/v2/aggs/ticker/AAPL/range/1/day/...?cursor=xyz",
        "status": "OK",
    }
    page2 = {"results": [], "status": "OK"}

    c = MassiveClient(api_key="mykey")
    c._client = AsyncMock()
    c._client.get = AsyncMock(side_effect=[_mock_response(page1), _mock_response(page2)])

    await c.get_bars("AAPL", 1, "day", "2024-01-01", "2024-01-01")

    second_params = c._client.get.call_args_list[1][1]["params"]
    assert second_params["apiKey"] == "mykey"


# ---------------------------------------------------------------------------
# MassiveClient — get_quote
# ---------------------------------------------------------------------------

_QUOTE_PAYLOAD = {
    "results": {
        "T": "AAPL",
        "P": 185.20,
        "S": 1,
        "p": 185.10,
        "s": 1,
        "t": 1704067200000000000,
    },
    "status": "OK",
}


@pytest.mark.asyncio
async def test_get_quote_returns_results():
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(_QUOTE_PAYLOAD)

    result = await c.get_quote("AAPL")

    assert result["T"] == "AAPL"


@pytest.mark.asyncio
async def test_get_quote_calls_correct_url():
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(_QUOTE_PAYLOAD)

    await c.get_quote("AAPL")

    url: str = c._client.get.call_args[0][0]
    assert "/v2/last/nbbo/AAPL" in url


@pytest.mark.asyncio
async def test_get_quote_includes_api_key():
    c = MassiveClient(api_key="qkey")
    c._client = _make_client_mock(_QUOTE_PAYLOAD)

    await c.get_quote("AAPL")

    params = c._client.get.call_args[1]["params"]
    assert params["apiKey"] == "qkey"


# ---------------------------------------------------------------------------
# MassiveClient — get_snapshot
# ---------------------------------------------------------------------------

_SNAPSHOT_PAYLOAD = {
    "ticker": {
        "ticker": "AAPL",
        "day": {"o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 1_000_000},
        "lastTrade": {"p": 186.5, "s": 100, "t": 1704067200000000000},
        "lastQuote": {"P": 186.6, "S": 1, "p": 186.4, "s": 1, "t": 1704067200000000000},
    },
    "status": "OK",
}


@pytest.mark.asyncio
async def test_get_snapshot_returns_ticker_key():
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(_SNAPSHOT_PAYLOAD)

    result = await c.get_snapshot("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["day"]["c"] == 186.5


@pytest.mark.asyncio
async def test_get_snapshot_calls_correct_url():
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(_SNAPSHOT_PAYLOAD)

    await c.get_snapshot("AAPL")

    url: str = c._client.get.call_args[0][0]
    assert "/v2/snapshot/locale/us/markets/stocks/tickers/AAPL" in url


@pytest.mark.asyncio
async def test_get_snapshot_includes_api_key():
    c = MassiveClient(api_key="snapkey")
    c._client = _make_client_mock(_SNAPSHOT_PAYLOAD)

    await c.get_snapshot("AAPL")

    params = c._client.get.call_args[1]["params"]
    assert params["apiKey"] == "snapkey"


# ---------------------------------------------------------------------------
# MassiveClient — get_top_movers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_top_movers_returns_list():
    payload = {"tickers": [{"ticker": "AAPL"}, {"ticker": "MSFT"}], "status": "OK"}
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(payload)

    result = await c.get_top_movers("gainers")

    assert len(result) == 2
    assert result[0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_get_top_movers_default_direction_is_gainers():
    payload = {"tickers": [], "status": "OK"}
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(payload)

    await c.get_top_movers()

    url: str = c._client.get.call_args[0][0]
    assert "gainers" in url


# ---------------------------------------------------------------------------
# MassiveClient — get_rsi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_rsi_calls_correct_url():
    payload = {"results": {"values": [{"timestamp": 1704067200000, "value": 62.5}]}}
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(payload)

    await c.get_rsi("AAPL", timespan="day", window=14)

    url: str = c._client.get.call_args[0][0]
    assert "/v1/indicators/rsi/AAPL" in url


@pytest.mark.asyncio
async def test_get_rsi_includes_api_key():
    payload = {"results": {"values": []}}
    c = MassiveClient(api_key="rsikey")
    c._client = _make_client_mock(payload)

    await c.get_rsi("AAPL")

    params = c._client.get.call_args[1]["params"]
    assert params["apiKey"] == "rsikey"


# ---------------------------------------------------------------------------
# MassiveClient — get_macd
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_macd_calls_correct_url():
    payload = {"results": {"values": []}}
    c = MassiveClient(api_key="k")
    c._client = _make_client_mock(payload)

    await c.get_macd("TSLA")

    url: str = c._client.get.call_args[0][0]
    assert "/v1/indicators/macd/TSLA" in url


@pytest.mark.asyncio
async def test_get_macd_includes_api_key():
    payload = {"results": {"values": []}}
    c = MassiveClient(api_key="macdkey")
    c._client = _make_client_mock(payload)

    await c.get_macd("TSLA")

    params = c._client.get.call_args[1]["params"]
    assert params["apiKey"] == "macdkey"


# ---------------------------------------------------------------------------
# MassiveClient — close
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_calls_aclose():
    c = MassiveClient(api_key="k")
    c._client = AsyncMock()
    c._client.aclose = AsyncMock()

    await c.close()

    c._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# MassiveDataSource — get_historical_bars (Bar mapping)
# ---------------------------------------------------------------------------

_RAW_BARS = [
    {"t": 1704067200000, "o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 1_000_000},
    {"t": 1704153600000, "o": 186.5, "h": 188.0, "l": 185.5, "c": 187.0, "v": 900_000},
]


@pytest.mark.asyncio
async def test_get_historical_bars_returns_bar_objects():
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=_RAW_BARS)

    source = MassiveDataSource(mock_client)
    bars = await source.get_historical_bars("AAPL", "day", "2024-01-01", "2024-01-03")

    assert len(bars) == 2
    from broker.models import Bar
    assert isinstance(bars[0], Bar)


@pytest.mark.asyncio
async def test_get_historical_bars_correct_ohlcv_mapping():
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=_RAW_BARS)

    source = MassiveDataSource(mock_client)
    bars = await source.get_historical_bars("AAPL", "day", "2024-01-01", "2024-01-03")

    bar = bars[0]
    assert bar.open == Decimal("185.0")
    assert bar.high == Decimal("187.5")
    assert bar.low == Decimal("184.0")
    assert bar.close == Decimal("186.5")
    assert bar.volume == 1_000_000


@pytest.mark.asyncio
async def test_get_historical_bars_timestamp_from_milliseconds():
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=_RAW_BARS)

    source = MassiveDataSource(mock_client)
    bars = await source.get_historical_bars("AAPL", "day", "2024-01-01", "2024-01-03")

    # t=1704067200000 ms = 2024-01-01 00:00:00 UTC
    bar = bars[0]
    assert bar.timestamp.year == 2024
    assert bar.timestamp.month == 1
    assert bar.timestamp.day == 1
    assert bar.timestamp.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_get_historical_bars_sorted_ascending():
    raw = [
        {"t": 1704153600000, "o": 186.5, "h": 188.0, "l": 185.5, "c": 187.0, "v": 900_000},
        {"t": 1704067200000, "o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 1_000_000},
    ]
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=raw)

    source = MassiveDataSource(mock_client)
    bars = await source.get_historical_bars("AAPL", "day", "2024-01-01", "2024-01-03")

    assert bars[0].timestamp < bars[1].timestamp


@pytest.mark.asyncio
async def test_get_historical_bars_symbol_embedded():
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=_RAW_BARS)
    sym = Symbol(ticker="AAPL")

    source = MassiveDataSource(mock_client)
    bars = await source.get_historical_bars("AAPL", "day", "2024-01-01", "2024-01-03", symbol=sym)

    assert bars[0].symbol.ticker == "AAPL"


@pytest.mark.asyncio
async def test_get_historical_bars_skips_malformed_entries(caplog):
    raw = [
        {"t": 1704067200000, "o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 1_000_000},
        {"bad": "entry"},  # missing "t" — should be skipped
    ]
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=raw)

    source = MassiveDataSource(mock_client)
    import logging
    with caplog.at_level(logging.WARNING):
        bars = await source.get_historical_bars("AAPL", "day", "2024-01-01", "2024-01-03")

    assert len(bars) == 1


# ---------------------------------------------------------------------------
# MassiveDataSource — get_quote (Quote mapping)
# ---------------------------------------------------------------------------

_SNAPSHOT_DATA = {
    "ticker": "AAPL",
    "day": {"o": 185.0, "h": 187.5, "l": 184.0, "c": 186.5, "v": 1_000_000},
    "lastTrade": {"p": 186.5, "s": 100, "t": 1704067200000000000},
    "lastQuote": {"P": 186.6, "S": 1, "p": 186.4, "s": 1, "t": 1704067200000000000},
}


@pytest.mark.asyncio
async def test_get_quote_returns_quote_object():
    from broker.models import Quote
    mock_client = AsyncMock()
    mock_client.get_snapshot = AsyncMock(return_value=_SNAPSHOT_DATA)

    source = MassiveDataSource(mock_client)
    sym = Symbol(ticker="AAPL")
    result = await source.get_quote(sym)

    assert isinstance(result, Quote)
    assert result.symbol == sym


@pytest.mark.asyncio
async def test_get_quote_extracts_last_trade_price():
    mock_client = AsyncMock()
    mock_client.get_snapshot = AsyncMock(return_value=_SNAPSHOT_DATA)

    source = MassiveDataSource(mock_client)
    result = await source.get_quote(Symbol(ticker="AAPL"))

    assert result.last == Decimal("186.5")


@pytest.mark.asyncio
async def test_get_quote_extracts_bid_ask():
    # Polygon lastQuote convention: P = ask price, p = bid price
    mock_client = AsyncMock()
    mock_client.get_snapshot = AsyncMock(return_value=_SNAPSHOT_DATA)

    source = MassiveDataSource(mock_client)
    result = await source.get_quote(Symbol(ticker="AAPL"))

    assert result.ask == Decimal("186.6")   # P field
    assert result.bid == Decimal("186.4")   # p field


@pytest.mark.asyncio
async def test_get_quote_extracts_volume():
    mock_client = AsyncMock()
    mock_client.get_snapshot = AsyncMock(return_value=_SNAPSHOT_DATA)

    source = MassiveDataSource(mock_client)
    result = await source.get_quote(Symbol(ticker="AAPL"))

    assert result.volume == 1_000_000


@pytest.mark.asyncio
async def test_get_quote_timestamp_from_nanoseconds():
    mock_client = AsyncMock()
    mock_client.get_snapshot = AsyncMock(return_value=_SNAPSHOT_DATA)

    source = MassiveDataSource(mock_client)
    result = await source.get_quote(Symbol(ticker="AAPL"))

    # 1704067200000000000 ns = 2024-01-01 00:00:00 UTC
    assert result.timestamp.year == 2024
    assert result.timestamp.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# MassiveDataSource — get_rsi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_rsi_returns_float():
    mock_client = AsyncMock()
    mock_client.get_rsi = AsyncMock(return_value={"values": [{"timestamp": 1704067200000, "value": 62.5}]})

    source = MassiveDataSource(mock_client)
    result = await source.get_rsi("AAPL")

    assert result == 62.5
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_get_rsi_returns_none_on_empty_values():
    mock_client = AsyncMock()
    mock_client.get_rsi = AsyncMock(return_value={"values": []})

    source = MassiveDataSource(mock_client)
    result = await source.get_rsi("AAPL")

    assert result is None


@pytest.mark.asyncio
async def test_get_rsi_returns_none_on_exception(caplog):
    mock_client = AsyncMock()
    mock_client.get_rsi = AsyncMock(side_effect=Exception("API error"))

    source = MassiveDataSource(mock_client)
    import logging
    with caplog.at_level(logging.WARNING):
        result = await source.get_rsi("AAPL")

    assert result is None


# ---------------------------------------------------------------------------
# MassiveDataSource — get_historical (DataBus-style period/timeframe)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_historical_maps_timeframe_to_timespan():
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=[])

    source = MassiveDataSource(mock_client)
    await source.get_historical(Symbol(ticker="AAPL"), timeframe="1d", period="3mo")

    call_kwargs = mock_client.get_bars.call_args
    # multiplier and timespan are positional args: ticker, mult, timespan, from, to
    assert call_kwargs[0][2] == "day"
    assert call_kwargs[0][1] == 1


@pytest.mark.asyncio
async def test_get_historical_maps_hourly_timeframe():
    mock_client = AsyncMock()
    mock_client.get_bars = AsyncMock(return_value=[])

    source = MassiveDataSource(mock_client)
    await source.get_historical(Symbol(ticker="AAPL"), timeframe="1h", period="1mo")

    call_kwargs = mock_client.get_bars.call_args
    assert call_kwargs[0][2] == "hour"
    assert call_kwargs[0][1] == 1


# ---------------------------------------------------------------------------
# MassiveDataSource — DataSource interface attributes
# ---------------------------------------------------------------------------

def test_source_name():
    source = MassiveDataSource(MagicMock())
    assert source.name == "massive"


def test_source_supports_quotes():
    source = MassiveDataSource(MagicMock())
    assert source.supports_quotes is True


def test_source_supports_historical():
    source = MassiveDataSource(MagicMock())
    assert source.supports_historical is True


def test_source_does_not_support_options():
    source = MassiveDataSource(MagicMock())
    assert source.supports_options is False
