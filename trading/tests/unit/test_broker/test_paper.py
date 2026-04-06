import pytest
import aiosqlite
from decimal import Decimal
from unittest.mock import AsyncMock

from broker.paper import PaperBroker
from storage.paper import PaperStore
from broker.interfaces import Broker, BrokerConnection, MarketDataProvider
from broker.models import (
    Symbol,
    AssetType,
    MarketOrder,
    LimitOrder,
    OrderSide,
    Quote,
    BrokerCapabilities,
)
from broker.paper import PaperOrderManager


class MockConnection(BrokerConnection):
    async def connect(self):
        pass

    async def disconnect(self):
        pass

    def is_connected(self):
        return True

    def on_disconnected(self, callback):
        pass

    async def reconnect(self):
        pass


class MockMarketData(MarketDataProvider):
    async def get_quote(self, symbol: Symbol) -> Quote:
        return Quote(
            symbol=symbol,
            bid=Decimal("150.0"),
            ask=Decimal("150.1"),
            last=Decimal("150.05"),
        )

    async def get_quotes(self, symbols):
        return []

    async def stream_quotes(self, symbols, callback):
        pass

    async def get_historical(self, symbol, timeframe, period):
        return []

    async def get_options_chain(self, symbol, expiry=None):
        pass

    async def get_contract_details(self, symbol):
        pass


class MockBroker(Broker):
    @property
    def connection(self):
        return MockConnection()

    @property
    def account(self):
        return None

    @property
    def orders(self):
        return None

    @property
    def market_data(self):
        return MockMarketData()

    def capabilities(self):
        return BrokerCapabilities()


@pytest.fixture
async def paper_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    yield store
    await db.close()


@pytest.fixture
def paper_broker(paper_store):
    return PaperBroker(MockBroker(), paper_store)


@pytest.mark.asyncio
async def test_paper_order_raises_on_no_price():
    """Paper broker should raise when no market data is available."""
    market_data = AsyncMock()
    market_data.get_quote = AsyncMock(
        return_value=Quote(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            bid=None,
            ask=None,
            last=None,
            volume=0,
        )
    )
    store = AsyncMock()

    mgr = PaperOrderManager(market_data, store)
    order = MarketOrder(
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        account_id="PAPER",
    )

    with pytest.raises(ValueError, match="market data"):
        await mgr.place_order("PAPER", order)


@pytest.mark.asyncio
class TestPaperBroker:
    async def test_capabilities(self, paper_broker):
        cap = paper_broker.capabilities()
        assert cap.stocks is True

    async def test_initial_balance(self, paper_broker):
        bal = await paper_broker.account.get_balances("PAPER")
        assert bal.net_liquidation == Decimal("100000.0")
        assert bal.cash == Decimal("100000.0")

    async def test_place_market_order_buy(self, paper_broker):
        sym = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
        order = MarketOrder(
            symbol=sym, side=OrderSide.BUY, quantity=Decimal("10"), account_id="PAPER"
        )

        # Place order
        res = await paper_broker.orders.place_order("PAPER", order)
        assert res.status.value == "FILLED"
        assert res.filled_quantity == Decimal("10")
        assert res.avg_fill_price == Decimal("150.1")  # Mock ask price

        # Check positions
        pos = await paper_broker.account.get_positions("PAPER")
        assert len(pos) == 1
        assert pos[0].symbol.ticker == "AAPL"
        assert pos[0].quantity == Decimal("10")
        assert pos[0].avg_cost == Decimal("150.1")

        # Check balance
        bal = await paper_broker.account.get_balances("PAPER")
        assert bal.cash == Decimal("100000.0") - (Decimal("10") * Decimal("150.1"))

    async def test_place_market_order_sell_short(self, paper_broker):
        sym = Symbol(ticker="MSFT", asset_type=AssetType.STOCK)
        order = MarketOrder(
            symbol=sym, side=OrderSide.SELL, quantity=Decimal("5"), account_id="PAPER"
        )

        res = await paper_broker.orders.place_order("PAPER", order)
        assert res.avg_fill_price == Decimal("150.0")  # Mock bid price

        pos = await paper_broker.account.get_positions("PAPER")
        assert len(pos) == 1
        assert pos[0].quantity == Decimal("-5")

    async def test_realized_pnl(self, paper_broker):
        sym = Symbol(ticker="TSLA", asset_type=AssetType.STOCK)

        # Buy 10 @ 150.1
        await paper_broker.orders.place_order(
            "PAPER",
            MarketOrder(
                symbol=sym,
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="PAPER",
            ),
        )

        # Sell 5 @ 160.0 (simulated via limit order at 160.0)
        await paper_broker.orders.place_order(
            "PAPER",
            LimitOrder(
                symbol=sym,
                side=OrderSide.SELL,
                quantity=Decimal("5"),
                account_id="PAPER",
                limit_price=Decimal("160.0"),
            ),
        )

        pos = await paper_broker.account.get_positions("PAPER")
        assert len(pos) == 1
        p = pos[0]
        assert p.quantity == Decimal("5")
        assert p.avg_cost == Decimal("150.1")
        # PnL = (160.0 - 150.1) * 5 = 9.9 * 5 = 49.5
        assert p.realized_pnl == Decimal("49.5")
