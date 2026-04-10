# tests/unit/data/test_exchange_client.py
from __future__ import annotations

from data.exchange_client import ExchangeClient, FetchResult, FetchError


class TestFetchResult:
    def test_is_complete_all_present(self):
        result = FetchResult(
            ohlcv=[{"close": 50000}],
            funding={"rate": 0.001},
            oi=1_000_000.0,
            orderbook={"bids": [], "asks": []},
        )
        assert result.is_complete is True

    def test_is_complete_partial(self):
        result = FetchResult(ohlcv=[{"close": 50000}])
        assert result.is_complete is False
        assert result.partial_success is True

    def test_empty_result(self):
        result = FetchResult()
        assert result.is_complete is False
        assert result.partial_success is False

    def test_available_data_types(self):
        result = FetchResult(ohlcv=[{"close": 50000}], funding={"rate": 0.001})
        assert set(result.available_data_types) == {"ohlcv", "funding"}

    def test_errors_tracked(self):
        result = FetchResult(
            errors=[FetchError(exchange="binance", data_type="oi", error="timeout")]
        )
        assert len(result.errors) == 1
        assert result.errors[0].exchange == "binance"


class TestExchangeClientNormalize:
    def test_btcusd_to_spot(self):
        client = ExchangeClient.__new__(ExchangeClient)
        assert client._format_spot("BTCUSD") == "BTC/USDT"
        assert client._format_spot("ETHUSD") == "ETH/USDT"

    def test_btcusd_to_perp(self):
        client = ExchangeClient.__new__(ExchangeClient)
        assert client._format_perp("BTCUSD") == "BTC/USDT:USDT"
