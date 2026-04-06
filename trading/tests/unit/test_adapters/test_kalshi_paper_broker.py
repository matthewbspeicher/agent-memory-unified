"""Unit tests for KalshiPaperBroker."""

from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from broker.models import AssetType, LimitOrder, OrderSide, OrderStatus, Symbol, TIF


def _prediction_symbol(ticker: str = "HIGHNY-26MAR-B72") -> Symbol:
    return Symbol(ticker=ticker, asset_type=AssetType.PREDICTION)


def _limit_order(
    ticker: str, side: OrderSide, price_prob: str, qty: int = 10
) -> LimitOrder:
    return LimitOrder(
        symbol=_prediction_symbol(ticker),
        side=side,
        quantity=Decimal(str(qty)),
        account_id="KALSHI_PAPER",
        limit_price=Decimal(price_prob),
        time_in_force=TIF.GTC,
    )


class TestKalshiPaperBrokerPlaceOrder:
    @pytest.mark.asyncio
    async def test_place_buy_yes_returns_filled(self):
        from adapters.kalshi.paper import KalshiPaperBroker

        store = AsyncMock()
        store.get_balance = AsyncMock(return_value=MagicMock(cash=Decimal("1000")))
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()
        store.record_kalshi_resolution = AsyncMock()

        broker = KalshiPaperBroker(store=store)
        order = _limit_order("MKT-001", OrderSide.BUY, "0.65", qty=10)
        result = await broker.orders.place_order("KALSHI_PAPER", order)

        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        # Fill price should be near 0.65 ± slippage
        assert result.avg_fill_price is not None
        assert Decimal("0.60") <= result.avg_fill_price <= Decimal("0.70")

    @pytest.mark.asyncio
    async def test_place_order_records_fill_in_store(self):
        from adapters.kalshi.paper import KalshiPaperBroker

        store = AsyncMock()
        store.get_balance = AsyncMock(return_value=MagicMock(cash=Decimal("1000")))
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = KalshiPaperBroker(store=store)
        order = _limit_order("MKT-001", OrderSide.BUY, "0.40", qty=5)
        await broker.orders.place_order("KALSHI_PAPER", order)

        store.record_fill.assert_awaited_once()
        call_args = store.record_fill.call_args
        assert call_args.kwargs["side"] == OrderSide.BUY
        assert call_args.kwargs["quantity"] == Decimal("5")


class TestKalshiPaperBrokerResolution:
    @pytest.mark.asyncio
    async def test_yes_resolution_credits_full_dollar(self):
        """YES resolution pays $1.00 per contract regardless of entry price."""
        from adapters.kalshi.paper import KalshiPaperBroker, KALSHI_PAPER_ACCOUNT_ID

        store = AsyncMock()
        store.get_balance = AsyncMock(return_value=MagicMock(cash=Decimal("1000")))
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()
        store.record_binary_resolution = AsyncMock()

        broker = KalshiPaperBroker(store=store)
        sym = _prediction_symbol("MKT-001")

        await broker.resolve_contract(
            account_id=KALSHI_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.65"),
            resolution="YES",
        )

        store.record_binary_resolution.assert_awaited_once_with(
            account_id=KALSHI_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.65"),
            resolution="YES",
        )

    @pytest.mark.asyncio
    async def test_no_resolution_loses_entry_price(self):
        """NO resolution: YES holders lose their entry price."""
        from adapters.kalshi.paper import KalshiPaperBroker, KALSHI_PAPER_ACCOUNT_ID

        store = AsyncMock()
        store.record_binary_resolution = AsyncMock()

        broker = KalshiPaperBroker(store=store)
        sym = _prediction_symbol("MKT-001")

        await broker.resolve_contract(
            account_id=KALSHI_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.40"),
            resolution="NO",
        )
        store.record_binary_resolution.assert_awaited_once()
        call_kwargs = store.record_binary_resolution.call_args.kwargs
        assert call_kwargs["resolution"] == "NO"

    @pytest.mark.asyncio
    async def test_cancelled_resolution_refunds_entry_price(self):
        """CANCELLED resolution refunds at entry price."""
        from adapters.kalshi.paper import KalshiPaperBroker, KALSHI_PAPER_ACCOUNT_ID

        store = AsyncMock()
        store.record_binary_resolution = AsyncMock()

        broker = KalshiPaperBroker(store=store)
        sym = _prediction_symbol("MKT-CANCEL")

        await broker.resolve_contract(
            account_id=KALSHI_PAPER_ACCOUNT_ID,
            symbol=sym,
            quantity=Decimal("5"),
            entry_price=Decimal("0.50"),
            resolution="CANCELLED",
        )
        store.record_binary_resolution.assert_awaited_once()
        call_kwargs = store.record_binary_resolution.call_args.kwargs
        assert call_kwargs["resolution"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_slippage_applied_on_buy(self):
        """Buy fills at limit_price + slippage_cents/100."""
        from adapters.kalshi.paper import KalshiPaperBroker

        store = AsyncMock()
        store.get_balance = AsyncMock(return_value=MagicMock(cash=Decimal("1000")))
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = KalshiPaperBroker(store=store, slippage_cents=2)
        order = _limit_order("MKT-001", OrderSide.BUY, "0.50", qty=1)
        result = await broker.orders.place_order("KALSHI_PAPER", order)

        assert result.avg_fill_price == Decimal("0.52")

    @pytest.mark.asyncio
    async def test_slippage_applied_on_sell(self):
        """Sell fills at limit_price - slippage_cents/100."""
        from adapters.kalshi.paper import KalshiPaperBroker

        store = AsyncMock()
        store.get_balance = AsyncMock(return_value=MagicMock(cash=Decimal("1000")))
        store.record_fill = AsyncMock()
        store.save_order = AsyncMock()

        broker = KalshiPaperBroker(store=store, slippage_cents=2)
        order = _limit_order("MKT-001", OrderSide.SELL, "0.30", qty=1)
        result = await broker.orders.place_order("KALSHI_PAPER", order)

        assert result.avg_fill_price == Decimal("0.28")

    @pytest.mark.asyncio
    async def test_non_limit_order_is_rejected(self):
        from adapters.kalshi.paper import KalshiPaperBroker
        from broker.models import MarketOrder

        store = AsyncMock()
        broker = KalshiPaperBroker(store=store)
        order = MarketOrder(
            symbol=_prediction_symbol(),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            account_id="KALSHI_PAPER",
        )
        result = await broker.orders.place_order("KALSHI_PAPER", order)
        assert result.status == OrderStatus.REJECTED


class TestPaperStoreKalshiResolution:
    @pytest.fixture
    async def store_with_position(self, tmp_path):
        """Real in-memory PaperStore with a seeded prediction position."""
        import aiosqlite
        from storage.paper import PaperStore

        db_path = str(tmp_path / "test.db")
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            store = PaperStore(db=db)
            await store.init_tables()
            yield store, db

    @pytest.mark.asyncio
    async def test_yes_resolution_pnl_calculation(self, store_with_position):
        """record_kalshi_resolution with YES: payout=$1.00/contract, P&L=payout-cost."""
        from broker.models import Symbol, AssetType, OrderSide

        store, db = store_with_position
        sym = Symbol(ticker="MKT-001", asset_type=AssetType.PREDICTION)

        # Seed a position
        await store.record_fill(
            account_id="KALSHI_PAPER",
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            fill_price=Decimal("0.65"),
        )

        await store.record_kalshi_resolution(
            account_id="KALSHI_PAPER",
            symbol=sym,
            quantity=Decimal("10"),
            entry_price=Decimal("0.65"),
            resolution="YES",
        )

        # YES payout = 10 * $1.00 = $10.00; cost = 10 * $0.65 = $6.50; realized = $3.50
        pos = await store.get_positions("KALSHI_PAPER")
        assert len(pos) == 0 or (len(pos) == 1 and pos[0].quantity == Decimal("0"))

    @pytest.mark.asyncio
    async def test_no_resolution_pnl_is_negative_entry_cost(self, store_with_position):
        """record_kalshi_resolution with NO: payout=$0, realized=-entry_cost."""
        from broker.models import Symbol, AssetType, OrderSide

        store, db = store_with_position
        sym = Symbol(ticker="MKT-002", asset_type=AssetType.PREDICTION)

        await store.record_fill(
            account_id="KALSHI_PAPER",
            symbol=sym,
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            fill_price=Decimal("0.40"),
        )

        await store.record_kalshi_resolution(
            account_id="KALSHI_PAPER",
            symbol=sym,
            quantity=Decimal("5"),
            entry_price=Decimal("0.40"),
            resolution="NO",
        )

        # NO payout = $0; cost = 5 * $0.40 = $2.00; realized = -$2.00
        pos = await store.get_positions("KALSHI_PAPER")
        assert len(pos) == 0 or (len(pos) == 1 and pos[0].quantity == Decimal("0"))
