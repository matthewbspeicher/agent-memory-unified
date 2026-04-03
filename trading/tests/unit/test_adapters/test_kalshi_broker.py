"""Unit tests for KalshiClient, KalshiBroker, and KalshiDataSource."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from broker.models import (
    AssetType, BrokerCapabilities, LimitOrder, OrderResult, OrderSide,
    OrderStatus, PredictionContract, Symbol, TIF,
)
from adapters.kalshi.broker import (
    KalshiBroker, KalshiAccount, KalshiMarketData, KalshiOrderManager,
    _cents_to_prob, _prob_to_cents,
)
from adapters.kalshi.data_source import KalshiDataSource


# ---------------------------------------------------------------------------
# Utility function tests (pure, no IO)
# ---------------------------------------------------------------------------

class TestProbabilityConversions:
    def test_cents_to_prob_midrange(self):
        assert _cents_to_prob(65) == Decimal("0.65")

    def test_cents_to_prob_zero(self):
        assert _cents_to_prob(0) == Decimal("0")

    def test_cents_to_prob_none(self):
        assert _cents_to_prob(None) is None

    def test_prob_to_cents_normal(self):
        assert _prob_to_cents(Decimal("0.72")) == 72

    def test_prob_to_cents_clamps_high(self):
        assert _prob_to_cents(Decimal("1.5")) == 99

    def test_prob_to_cents_clamps_low(self):
        assert _prob_to_cents(Decimal("0.0")) == 1

    def test_prob_to_cents_roundtrip(self):
        for cents in [10, 35, 50, 78, 95]:
            assert _prob_to_cents(_cents_to_prob(cents)) == cents


# ---------------------------------------------------------------------------
# Domain model tests
# ---------------------------------------------------------------------------

class TestPredictionContract:
    def _make_contract(self, yes_bid=40, yes_ask=42, yes_last=41):
        return PredictionContract(
            ticker="TESTMKT-26MAR-B50",
            title="Will something happen by March 26?",
            category="economics",
            close_time=datetime(2026, 3, 26, tzinfo=timezone.utc),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            yes_last=yes_last,
        )

    def test_as_symbol(self):
        contract = self._make_contract()
        sym = contract.as_symbol
        assert sym.ticker == "TESTMKT-26MAR-B50"
        assert sym.asset_type == AssetType.PREDICTION

    def test_mid_probability_from_bid_ask(self):
        contract = self._make_contract(yes_bid=40, yes_ask=60)
        assert contract.mid_probability == 0.50

    def test_mid_probability_fallback_to_last(self):
        contract = self._make_contract(yes_bid=None, yes_ask=None, yes_last=75)
        assert contract.mid_probability == 0.75

    def test_mid_probability_none_when_no_data(self):
        contract = PredictionContract(
            ticker="X", title="X", category="x",
            close_time=datetime.now(timezone.utc),
        )
        assert contract.mid_probability is None


class TestBrokerCapabilities:
    def test_kalshi_capabilities(self):
        broker = KalshiBroker(demo=True)
        caps = broker.capabilities()
        assert isinstance(caps, BrokerCapabilities)
        assert caps.prediction_markets is True
        assert caps.stocks is False
        assert caps.options is False


# ---------------------------------------------------------------------------
# KalshiAccount tests
# ---------------------------------------------------------------------------

class TestKalshiAccount:
    @pytest.mark.asyncio
    async def test_get_accounts_returns_kalshi_account(self):
        client = MagicMock()
        account = KalshiAccount(client)
        accounts = await account.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].account_id == "KALSHI"

    @pytest.mark.asyncio
    async def test_get_balances_converts_cents(self):
        client = AsyncMock()
        client.get_balance.return_value = {
            "available_balance": 50000,   # $500.00
            "portfolio_value": 120000,    # $1200.00
        }
        account = KalshiAccount(client)
        bal = await account.get_balances("KALSHI")
        assert bal.net_liquidation == Decimal("1200.00")
        assert bal.cash == Decimal("500.00")
        assert bal.buying_power == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_get_positions_skips_zero_qty(self):
        client = AsyncMock()
        client.get_positions.return_value = [
            {"ticker": "MKTX", "position": 0, "market_exposure": 0},
            {"ticker": "MKTY", "position": 5, "market_exposure": 300, "total_traded": 250},
        ]
        account = KalshiAccount(client)
        positions = await account.get_positions("KALSHI")
        assert len(positions) == 1
        assert positions[0].symbol.ticker == "MKTY"
        assert positions[0].symbol.asset_type == AssetType.PREDICTION
        assert positions[0].quantity == Decimal("5")


# ---------------------------------------------------------------------------
# KalshiMarketData tests
# ---------------------------------------------------------------------------

class TestKalshiMarketData:
    @pytest.mark.asyncio
    async def test_get_quote_from_orderbook(self):
        client = AsyncMock()
        client.get_orderbook.return_value = {
            "yes": [[65, 100], [64, 200]],   # best YES bid = 65¢
            "no":  [[40, 150]],              # best NO bid = 40¢ → YES ask = 60¢
        }
        client.get_trades.return_value = [{"yes_price": 63}]

        md = KalshiMarketData(client)
        sym = Symbol(ticker="HIGHNY-26MAR-B72", asset_type=AssetType.PREDICTION)
        quote = await md.get_quote(sym)

        assert quote.bid == Decimal("0.65")
        assert quote.ask == Decimal("0.60")
        assert quote.last == Decimal("0.63")

    @pytest.mark.asyncio
    async def test_get_quote_handles_empty_orderbook(self):
        client = AsyncMock()
        client.get_orderbook.return_value = {"yes": [], "no": []}
        client.get_trades.return_value = []
        md = KalshiMarketData(client)
        sym = Symbol(ticker="EMPTY", asset_type=AssetType.PREDICTION)
        quote = await md.get_quote(sym)
        assert quote.bid is None
        assert quote.ask is None
        assert quote.last is None


# ---------------------------------------------------------------------------
# KalshiOrderManager tests
# ---------------------------------------------------------------------------

class TestKalshiOrderManager:
    @pytest.mark.asyncio
    async def test_place_limit_order_buy_yes(self):
        client = AsyncMock()
        client.create_order.return_value = {
            "order_id": "ord-001",
            "status": "resting",
            "contracts_filled": 0,
        }
        mgr = KalshiOrderManager(client)
        order = LimitOrder(
            symbol=Symbol(ticker="HIGHNY-26MAR-B72", asset_type=AssetType.PREDICTION),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id="KALSHI",
            limit_price=Decimal("0.65"),
        )
        result = await mgr.place_order("KALSHI", order)
        client.create_order.assert_called_once_with(
            ticker="HIGHNY-26MAR-B72",
            side="yes",
            count=10,
            price=65,
        )
        assert result.order_id == "ord-001"
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_place_limit_order_sell_maps_to_no(self):
        client = AsyncMock()
        client.create_order.return_value = {"order_id": "ord-002", "status": "resting", "contracts_filled": 0}
        mgr = KalshiOrderManager(client)
        order = LimitOrder(
            symbol=Symbol(ticker="HIGHNY-26MAR-B72", asset_type=AssetType.PREDICTION),
            side=OrderSide.SELL,
            quantity=Decimal("5"),
            account_id="KALSHI",
            limit_price=Decimal("0.30"),
        )
        await mgr.place_order("KALSHI", order)
        call_kwargs = client.create_order.call_args
        assert call_kwargs.kwargs["side"] == "no"

    @pytest.mark.asyncio
    async def test_market_order_raises(self):
        from broker.models import MarketOrder
        client = AsyncMock()
        mgr = KalshiOrderManager(client)
        order = MarketOrder(
            symbol=Symbol(ticker="X", asset_type=AssetType.PREDICTION),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            account_id="KALSHI",
        )
        with pytest.raises(ValueError, match="limit orders"):
            await mgr.place_order("KALSHI", order)

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        client = AsyncMock()
        client.cancel_order.return_value = {"status": "canceled"}
        mgr = KalshiOrderManager(client)
        result = await mgr.cancel_order("ord-123")
        assert result.status == OrderStatus.CANCELLED
        assert result.order_id == "ord-123"


# ---------------------------------------------------------------------------
# KalshiDataSource tests
# ---------------------------------------------------------------------------

class TestKalshiDataSource:
    def _sample_market(self, ticker="MKT-001", yes_bid=45, yes_ask=47, volume=500):
        return {
            "ticker": ticker,
            "title": "Will the Fed raise rates in 2026?",
            "category": "economics",
            "close_time": "2026-12-31T23:59:59Z",
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "last_price": 46,
            "open_interest": 1000,
            "volume_24h": volume,
        }

    @pytest.mark.asyncio
    async def test_get_markets_returns_contracts(self):
        client = AsyncMock()
        client.get_all_markets.return_value = [
            self._sample_market("MKT-001"),
            self._sample_market("MKT-002", yes_bid=80, yes_ask=82),
        ]
        source = KalshiDataSource(client)
        contracts = await source.get_markets(category="economics")
        assert len(contracts) == 2
        assert all(isinstance(c, PredictionContract) for c in contracts)
        assert contracts[0].ticker == "MKT-001"
        assert contracts[0].yes_bid == 45

    @pytest.mark.asyncio
    async def test_get_markets_skips_malformed(self):
        client = AsyncMock()
        client.get_all_markets.return_value = [
            self._sample_market("MKT-001"),
            {},  # missing ticker — should be skipped silently
        ]
        source = KalshiDataSource(client)
        contracts = await source.get_markets()
        assert len(contracts) == 1

    @pytest.mark.asyncio
    async def test_get_quote_maps_to_probability(self):
        client = AsyncMock()
        client.get_orderbook.return_value = {
            "yes": [[60, 100]],
            "no":  [[45, 100]],
        }
        client.get_trades.return_value = [{"yes_price": 58}]
        source = KalshiDataSource(client)
        sym = Symbol(ticker="MKT-001", asset_type=AssetType.PREDICTION)
        quote = await source.get_quote(sym)
        assert quote is not None
        assert quote.bid == Decimal("0.60")
        assert quote.last == Decimal("0.58")

    @pytest.mark.asyncio
    async def test_get_quote_returns_none_for_non_prediction_symbol(self):
        client = AsyncMock()
        source = KalshiDataSource(client)
        sym = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
        result = await source.get_quote(sym)
        assert result is None
        client.get_orderbook.assert_not_called()
