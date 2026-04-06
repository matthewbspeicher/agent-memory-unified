import pytest
from decimal import Decimal
import uuid

from execution.arbitrage import (
    ArbCoordinator,
    ArbTrade,
    ArbLeg,
    ArbState,
    SequencingStrategy,
)
from broker.models import Symbol, AssetType, LimitOrder, OrderSide, TIF
from adapters.kalshi.paper import KalshiPaperBroker, KALSHI_PAPER_ACCOUNT_ID
from adapters.polymarket.paper import PolymarketPaperBroker, POLYMARKET_PAPER_ACCOUNT_ID
from storage.paper import PaperStore
from storage.arbitrage import ArbStore
import aiosqlite
from config import Config


@pytest.fixture
async def paper_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    yield store
    await db.close()


@pytest.fixture
async def arb_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("""
        CREATE TABLE IF NOT EXISTS arb_trades (
            id TEXT PRIMARY KEY,
            symbol_a TEXT NOT NULL,
            symbol_b TEXT NOT NULL,
            state TEXT NOT NULL,
            sequencing TEXT NOT NULL,
            expected_profit_bps INTEGER NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS arb_legs (
            trade_id TEXT NOT NULL,
            leg_name TEXT NOT NULL,
            broker_id TEXT NOT NULL,
            order_data TEXT NOT NULL,
            fill_price TEXT,
            fill_quantity TEXT NOT NULL,
            status TEXT NOT NULL,
            external_order_id TEXT,
            PRIMARY KEY (trade_id, leg_name)
        )
    """)
    await db.commit()
    store = ArbStore(db)
    yield store
    await db.close()


@pytest.mark.asyncio
async def test_arbitrage_e2e_dual_paper(paper_store, arb_store):
    kalshi_broker = KalshiPaperBroker(store=paper_store)
    await kalshi_broker.connection.connect()

    poly_broker = PolymarketPaperBroker(store=paper_store)
    await poly_broker.connection.connect()

    settings = Config()

    coordinator = ArbCoordinator(
        brokers={"kalshi": kalshi_broker, "polymarket": poly_broker},
        store=arb_store,
        config=settings,
    )

    sym_a = Symbol(ticker="TEST-YES", asset_type=AssetType.PREDICTION)
    sym_b = Symbol(ticker="0x123", asset_type=AssetType.PREDICTION)

    order_a = LimitOrder(
        symbol=sym_a,
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        limit_price=Decimal("0.45"),
        account_id=KALSHI_PAPER_ACCOUNT_ID,
        time_in_force=TIF.GTC,
    )

    order_b = LimitOrder(
        symbol=sym_b,
        side=OrderSide.SELL,
        quantity=Decimal("10"),
        limit_price=Decimal("0.55"),
        account_id=POLYMARKET_PAPER_ACCOUNT_ID,
        time_in_force=TIF.GTC,
    )

    leg_a = ArbLeg(broker_id="kalshi", order=order_a)
    leg_b = ArbLeg(broker_id="polymarket", order=order_b)

    trade = ArbTrade(
        id=str(uuid.uuid4()),
        symbol_a=sym_a.ticker,
        symbol_b=sym_b.ticker,
        leg_a=leg_a,
        leg_b=leg_b,
        sequencing=SequencingStrategy.KALSHI_FIRST,
        expected_profit_bps=1000,
    )

    # Execute the arb
    success = await coordinator.execute_arbitrage(trade)
    assert success is True

    # Verify the final state
    assert trade.state == ArbState.COMPLETED
    assert trade.leg_a.status == "filled"
    assert trade.leg_b.status == "filled"
