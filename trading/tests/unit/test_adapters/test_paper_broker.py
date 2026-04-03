"""Unit tests for adapters/paper/broker.py — SimulatedBroker."""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from broker.models import (
    AccountBalance,
    AssetType,
    BrokerCapabilities,
    LimitOrder,
    MarketOrder,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    Quote,
    Symbol,
)
from adapters.paper.broker import (
    PaperConnection,
    PaperMarketData,
    PaperOrderManager,
    SimulatedBroker,
    PAPER_ACCOUNT_ID,
)
from storage.paper import PaperStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stock(ticker: str) -> Symbol:
    return Symbol(ticker=ticker, asset_type=AssetType.STOCK)


def _quote(ticker: str, bid="99.00", ask="101.00", last="100.00") -> Quote:
    return Quote(
        symbol=_stock(ticker),
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal(last),
    )


def _make_store() -> MagicMock:
    store = MagicMock(spec=PaperStore)
    store._get_db = AsyncMock()
    store.record_fill = AsyncMock()
    store.save_order = AsyncMock()
    store.get_balance = AsyncMock(
        return_value=AccountBalance(
            account_id=PAPER_ACCOUNT_ID,
            net_liquidation=Decimal("10000"),
            buying_power=Decimal("10000"),
            cash=Decimal("10000"),
            maintenance_margin=Decimal("0"),
        )
    )
    store.get_positions = AsyncMock(return_value=[])
    store.get_order_history = AsyncMock(return_value=[])
    return store


def _make_db_mock():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# PaperConnection tests
# ---------------------------------------------------------------------------

class TestPaperConnection:
    @pytest.mark.asyncio
    async def test_connect_sets_connected(self):
        conn = PaperConnection()
        assert not conn.is_connected()
        await conn.connect()
        assert conn.is_connected()

    @pytest.mark.asyncio
    async def test_disconnect_clears_connected_and_fires_callbacks(self):
        conn = PaperConnection()
        await conn.connect()
        fired = []
        conn.on_disconnected(lambda: fired.append(1))
        await conn.disconnect()
        assert not conn.is_connected()
        assert fired == [1]

    @pytest.mark.asyncio
    async def test_reconnect_restores_connection(self):
        conn = PaperConnection()
        await conn.connect()
        await conn.disconnect()
        await conn.reconnect()
        assert conn.is_connected()


# ---------------------------------------------------------------------------
# PaperMarketData tests
# ---------------------------------------------------------------------------

class TestPaperMarketData:
    @pytest.mark.asyncio
    async def test_get_quote_delegates_to_data_bus(self):
        bus = AsyncMock()
        bus.get_quote = AsyncMock(return_value=_quote("AAPL"))
        md = PaperMarketData(data_bus=bus)
        q = await md.get_quote(_stock("AAPL"))
        assert q is not None
        assert q.symbol.ticker == "AAPL"
        bus.get_quote.assert_called_once_with(_stock("AAPL"))

    @pytest.mark.asyncio
    async def test_get_quote_returns_none_when_no_bus(self):
        md = PaperMarketData(data_bus=None)
        result = await md.get_quote(_stock("AAPL"))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_quote_returns_none_on_bus_exception(self):
        bus = AsyncMock()
        bus.get_quote = AsyncMock(side_effect=RuntimeError("bus error"))
        md = PaperMarketData(data_bus=bus)
        result = await md.get_quote(_stock("AAPL"))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_quotes_skips_none_results(self):
        bus = AsyncMock()
        bus.get_quote = AsyncMock(side_effect=[_quote("AAPL"), None])
        md = PaperMarketData(data_bus=bus)
        results = await md.get_quotes([_stock("AAPL"), _stock("MSFT")])
        assert len(results) == 1
        assert results[0].symbol.ticker == "AAPL"


# ---------------------------------------------------------------------------
# PaperOrderManager — fill simulation
# ---------------------------------------------------------------------------

class TestPaperOrderManager:
    def _make_manager(self, quote: Quote | None = None):
        md = AsyncMock(spec=PaperMarketData)
        md.get_quote = AsyncMock(return_value=quote)
        store = _make_store()
        db = _make_db_mock()
        store._get_db = AsyncMock(return_value=db)
        return PaperOrderManager(md, store), store, db

    @pytest.mark.asyncio
    async def test_buy_market_order_fills_at_ask(self):
        q = _quote("AAPL", bid="99.00", ask="101.00", last="100.00")
        mgr, store, db = self._make_manager(q)

        order = MarketOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id=PAPER_ACCOUNT_ID,
        )
        result = await mgr.place_order(PAPER_ACCOUNT_ID, order)

        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        # Fill price should be >= ask (ask + slippage)
        assert result.avg_fill_price is not None
        assert result.avg_fill_price >= Decimal("101.00")

    @pytest.mark.asyncio
    async def test_sell_market_order_fills_at_bid(self):
        q = _quote("AAPL", bid="99.00", ask="101.00", last="100.00")
        mgr, store, db = self._make_manager(q)

        order = MarketOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.SELL,
            quantity=Decimal("5"),
            account_id=PAPER_ACCOUNT_ID,
        )
        result = await mgr.place_order(PAPER_ACCOUNT_ID, order)

        assert result.status == OrderStatus.FILLED
        # Fill price should be <= bid (bid - slippage)
        assert result.avg_fill_price is not None
        assert result.avg_fill_price <= Decimal("99.00")

    @pytest.mark.asyncio
    async def test_limit_order_fills_at_limit_price_with_slippage(self):
        q = _quote("AAPL")
        mgr, store, db = self._make_manager(q)

        order = LimitOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("3"),
            account_id=PAPER_ACCOUNT_ID,
            limit_price=Decimal("100.00"),
        )
        result = await mgr.place_order(PAPER_ACCOUNT_ID, order)

        assert result.status == OrderStatus.FILLED
        # Limit BUY: fill = limit_price + slippage (0–0.1%)
        assert result.avg_fill_price is not None
        assert result.avg_fill_price >= Decimal("100.00")
        # Slippage never exceeds 0.1%
        assert result.avg_fill_price <= Decimal("100.00") * Decimal("1.001") + Decimal("0.01")

    @pytest.mark.asyncio
    async def test_fill_includes_slippage(self):
        """Slippage must be deterministically bounded to 0–0.1%."""
        q = _quote("AAPL", ask="100.00")
        mgr, store, db = self._make_manager(q)
        order = MarketOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            account_id=PAPER_ACCOUNT_ID,
        )

        # Run multiple times — all fills should be in the expected range
        for _ in range(20):
            result = await mgr.place_order(PAPER_ACCOUNT_ID, order)
            assert Decimal("100.00") <= result.avg_fill_price <= Decimal("100.101")

    @pytest.mark.asyncio
    async def test_order_rejected_when_no_market_data(self):
        mgr, store, db = self._make_manager(quote=None)

        order = MarketOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            account_id=PAPER_ACCOUNT_ID,
        )
        result = await mgr.place_order(PAPER_ACCOUNT_ID, order)
        assert result.status == OrderStatus.REJECTED
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_place_order_persists_fill_and_order(self):
        q = _quote("AAPL")
        mgr, store, db = self._make_manager(q)

        order = MarketOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id=PAPER_ACCOUNT_ID,
        )
        result = await mgr.place_order(PAPER_ACCOUNT_ID, order)

        store.record_fill.assert_called_once()
        store.save_order.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_order_update_callback_fires(self):
        q = _quote("AAPL")
        mgr, store, db = self._make_manager(q)

        received: list[OrderResult] = []
        mgr.on_order_update(received.append)

        order = MarketOrder(
            symbol=_stock("AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            account_id=PAPER_ACCOUNT_ID,
        )
        await mgr.place_order(PAPER_ACCOUNT_ID, order)
        assert len(received) == 1
        assert received[0].status == OrderStatus.FILLED


# ---------------------------------------------------------------------------
# SimulatedBroker — composite tests
# ---------------------------------------------------------------------------

class TestSimulatedBroker:
    def _make_broker(self, balance: float = 10_000.0) -> tuple[SimulatedBroker, MagicMock]:
        store = _make_store()
        db = _make_db_mock()
        store._get_db = AsyncMock(return_value=db)
        broker = SimulatedBroker(store=store, data_bus=None, initial_balance=balance)
        return broker, store

    @pytest.mark.asyncio
    async def test_capabilities_include_stocks_and_prediction_markets(self):
        broker, _ = self._make_broker()
        caps = broker.capabilities()
        assert isinstance(caps, BrokerCapabilities)
        assert caps.stocks is True
        assert caps.prediction_markets is True

    @pytest.mark.asyncio
    async def test_connection_is_paper_connection(self):
        broker, _ = self._make_broker()
        await broker.connection.connect()
        assert broker.connection.is_connected()

    @pytest.mark.asyncio
    async def test_get_accounts_returns_paper_account(self):
        broker, _ = self._make_broker()
        accounts = await broker.account.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].account_id == PAPER_ACCOUNT_ID

    @pytest.mark.asyncio
    async def test_get_balance_returns_initial_balance(self):
        broker, store = self._make_broker(balance=5000.0)
        bal = await broker.account.get_balances(PAPER_ACCOUNT_ID)
        assert bal.cash == Decimal("10000")   # from mocked store

    @pytest.mark.asyncio
    async def test_get_positions_returns_empty_initially(self):
        broker, store = self._make_broker()
        positions = await broker.account.get_positions(PAPER_ACCOUNT_ID)
        assert positions == []

    @pytest.mark.asyncio
    async def test_reset_clears_positions_and_restores_balance(self):
        broker, store = self._make_broker(balance=7500.0)
        db = _make_db_mock()
        store._get_db = AsyncMock(return_value=db)
        # executescript is not on AsyncMock by default, mock it explicitly
        db.executescript = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        await broker.reset()
        db.executescript.assert_called_once()
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_buy_order_reduces_balance_via_record_fill(self):
        """Verify that placing a BUY order calls record_fill to update cash."""
        bus = AsyncMock()
        bus.get_quote = AsyncMock(return_value=_quote("MSFT", ask="200.00"))
        store = _make_store()
        db = _make_db_mock()
        store._get_db = AsyncMock(return_value=db)
        broker = SimulatedBroker(store=store, data_bus=bus, initial_balance=10_000.0)

        order = MarketOrder(
            symbol=_stock("MSFT"),
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            account_id=PAPER_ACCOUNT_ID,
        )
        result = await broker.orders.place_order(PAPER_ACCOUNT_ID, order)
        assert result.status == OrderStatus.FILLED
        # record_fill must have been called to debit cash
        store.record_fill.assert_called_once()
        call_args = store.record_fill.call_args
        assert call_args.args[3] == Decimal("10")   # quantity
        assert call_args.args[2] == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_sell_order_calls_record_fill_with_sell_side(self):
        """Verify that placing a SELL order calls record_fill with SELL side."""
        bus = AsyncMock()
        bus.get_quote = AsyncMock(return_value=_quote("MSFT", bid="198.00"))
        store = _make_store()
        db = _make_db_mock()
        store._get_db = AsyncMock(return_value=db)
        broker = SimulatedBroker(store=store, data_bus=bus, initial_balance=10_000.0)

        order = MarketOrder(
            symbol=_stock("MSFT"),
            side=OrderSide.SELL,
            quantity=Decimal("5"),
            account_id=PAPER_ACCOUNT_ID,
        )
        result = await broker.orders.place_order(PAPER_ACCOUNT_ID, order)
        assert result.status == OrderStatus.FILLED
        store.record_fill.assert_called_once()
        call_args = store.record_fill.call_args
        assert call_args.args[2] == OrderSide.SELL
