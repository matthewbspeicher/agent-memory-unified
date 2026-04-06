"""Unit tests for PolymarketPaperBroker."""

from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from broker.models import (
    AssetType,
    LimitOrder,
    MarketOrder,
    OrderSide,
    OrderStatus,
    Symbol,
    TIF,
)


def _prediction_symbol(ticker: str = "0xABC123") -> Symbol:
    return Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)


def _limit_order(
    ticker: str, side: OrderSide, price_prob: str, qty: int = 10
) -> LimitOrder:
    return LimitOrder(
        symbol=_prediction_symbol(ticker),
        side=side,
        quantity=Decimal(str(qty)),
        account_id="POLYMARKET_PAPER",
        limit_price=Decimal(price_prob),
        time_in_force=TIF.GTC,
    )


class TestPolymarketPaperBrokerPlaceOrder:
    @pytest.mark.asyncio
    async def test_place_buy_returns_filled(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = PolymarketPaperBroker(store=store)
        order = _limit_order("0xABC", OrderSide.BUY, "0.65", qty=10)
        result = await broker.orders.place_order("POLYMARKET_PAPER", order)

        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        assert result.avg_fill_price is not None
        assert Decimal("0.60") <= result.avg_fill_price <= Decimal("0.70")

    @pytest.mark.asyncio
    async def test_place_order_records_fill_in_store(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = PolymarketPaperBroker(store=store)
        order = _limit_order("0xABC", OrderSide.BUY, "0.40", qty=5)
        await broker.orders.place_order("POLYMARKET_PAPER", order)

        store.record_fill.assert_awaited_once()
        call_args = store.record_fill.call_args
        assert call_args.kwargs["side"] == OrderSide.BUY
        assert call_args.kwargs["quantity"] == Decimal("5")

    @pytest.mark.asyncio
    async def test_non_limit_order_is_rejected(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        broker = PolymarketPaperBroker(store=store)
        order = MarketOrder(
            symbol=_prediction_symbol(),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            account_id="POLYMARKET_PAPER",
        )
        result = await broker.orders.place_order("POLYMARKET_PAPER", order)
        assert result.status == OrderStatus.REJECTED


class TestPolymarketPaperBrokerSlippage:
    @pytest.mark.asyncio
    async def test_slippage_applied_on_buy(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = PolymarketPaperBroker(store=store, slippage_cents=2)
        order = _limit_order("0xABC", OrderSide.BUY, "0.50", qty=1)
        result = await broker.orders.place_order("POLYMARKET_PAPER", order)

        assert result.avg_fill_price == Decimal("0.52")

    @pytest.mark.asyncio
    async def test_slippage_applied_on_sell(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = PolymarketPaperBroker(store=store, slippage_cents=2)
        order = _limit_order("0xABC", OrderSide.SELL, "0.30", qty=1)
        result = await broker.orders.place_order("POLYMARKET_PAPER", order)

        assert result.avg_fill_price == Decimal("0.28")

    @pytest.mark.asyncio
    async def test_slippage_clamped_to_bounds(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = PolymarketPaperBroker(store=store, slippage_cents=5)
        order = _limit_order("0xABC", OrderSide.SELL, "0.03", qty=1)
        result = await broker.orders.place_order("POLYMARKET_PAPER", order)

        assert result.avg_fill_price == Decimal("0.01")


class TestPolymarketPaperBrokerResolution:
    @pytest.mark.asyncio
    async def test_yes_resolution(self):
        from adapters.polymarket.paper import (
            PolymarketPaperBroker,
            POLYMARKET_PAPER_ACCOUNT_ID,
        )

        store = AsyncMock()
        store.record_binary_resolution = AsyncMock()

        broker = PolymarketPaperBroker(store=store)
        sym = _prediction_symbol("0xABC")

        await broker.resolve_contract(
            account_id=POLYMARKET_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.65"),
            resolution="YES",
        )

        store.record_binary_resolution.assert_awaited_once_with(
            account_id=POLYMARKET_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.65"),
            resolution="YES",
        )

    @pytest.mark.asyncio
    async def test_no_resolution(self):
        from adapters.polymarket.paper import (
            PolymarketPaperBroker,
            POLYMARKET_PAPER_ACCOUNT_ID,
        )

        store = AsyncMock()
        store.record_binary_resolution = AsyncMock()

        broker = PolymarketPaperBroker(store=store)
        sym = _prediction_symbol("0xABC")

        await broker.resolve_contract(
            account_id=POLYMARKET_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.40"),
            resolution="NO",
        )
        store.record_binary_resolution.assert_awaited_once()
        assert store.record_binary_resolution.call_args.kwargs["resolution"] == "NO"

    @pytest.mark.asyncio
    async def test_cancelled_resolution(self):
        from adapters.polymarket.paper import (
            PolymarketPaperBroker,
            POLYMARKET_PAPER_ACCOUNT_ID,
        )

        store = AsyncMock()
        store.record_binary_resolution = AsyncMock()

        broker = PolymarketPaperBroker(store=store)
        sym = _prediction_symbol("0xCANCEL")

        await broker.resolve_contract(
            account_id=POLYMARKET_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("5"),
            entry_price=Decimal("0.50"),
            resolution="CANCELLED",
        )
        store.record_binary_resolution.assert_awaited_once()
        assert (
            store.record_binary_resolution.call_args.kwargs["resolution"] == "CANCELLED"
        )


class TestPolymarketPaperBrokerCapabilities:
    @pytest.mark.asyncio
    async def test_capabilities_prediction_markets(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        broker = PolymarketPaperBroker(store=store)
        caps = broker.capabilities()
        assert caps.prediction_markets is True

    @pytest.mark.asyncio
    async def test_always_connected(self):
        from adapters.polymarket.paper import PolymarketPaperBroker

        store = AsyncMock()
        broker = PolymarketPaperBroker(store=store)
        assert broker.connection.is_connected() is True
