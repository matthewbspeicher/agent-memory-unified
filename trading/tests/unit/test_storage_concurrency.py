import asyncio
import pytest
import aiosqlite
from decimal import Decimal
from storage.arbitrage import ArbStore
from execution.models import ArbTrade, ArbLeg, ArbState
from broker.models import OrderBase, Symbol, AssetType


@pytest.fixture
async def db_conn():
    async with aiosqlite.connect(":memory:") as db:
        db.row_factory = aiosqlite.Row
        # Initialize schema
        await db.execute("""
            CREATE TABLE arb_trades (
                id TEXT PRIMARY KEY,
                symbol_a TEXT NOT NULL,
                symbol_b TEXT NOT NULL,
                expected_profit_bps INTEGER NOT NULL,
                sequencing TEXT NOT NULL,
                state TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE arb_legs (
                trade_id TEXT NOT NULL REFERENCES arb_trades(id) ON DELETE CASCADE,
                leg_name TEXT NOT NULL,
                broker_id TEXT NOT NULL,
                order_data TEXT NOT NULL,
                fill_price TEXT,
                fill_quantity TEXT DEFAULT '0',
                status TEXT DEFAULT 'pending',
                external_order_id TEXT,
                PRIMARY KEY (trade_id, leg_name)
            )
        """)
        await db.commit()
        yield db


@pytest.mark.asyncio
async def test_concurrent_leg_updates(db_conn):
    store = ArbStore(db_conn)

    # 1. Setup a trade
    symbol_a = Symbol(ticker="K-1", asset_type=AssetType.PREDICTION)
    symbol_b = Symbol(ticker="P-1", asset_type=AssetType.PREDICTION)

    leg_a = ArbLeg(
        broker_id="kalshi",
        order=OrderBase(
            symbol=symbol_a, side="BUY", quantity=Decimal("10"), account_id="U123"
        ),
    )
    leg_b = ArbLeg(
        broker_id="polymarket",
        order=OrderBase(
            symbol=symbol_b, side="SELL", quantity=Decimal("10"), account_id="U123"
        ),
    )

    trade = ArbTrade(
        id="concurrent-123",
        symbol_a="K-1",
        symbol_b="P-1",
        leg_a=leg_a,
        leg_b=leg_b,
        expected_profit_bps=50,
        state=ArbState.CONCURRENT_PENDING,
    )

    await store.save_trade(trade)

    # 2. Define concurrent update tasks
    async def update_a():
        # Artificial delay to increase overlap risk if not atomic
        await asyncio.sleep(0.01)
        new_leg_a = ArbLeg(
            broker_id="kalshi",
            order=leg_a.order,
            fill_price=Decimal("0.55"),
            fill_quantity=Decimal("10"),
            status="filled",
            external_order_id="ext-a",
        )
        await store.update_leg_atomic(trade.id, "leg_a", new_leg_a)

    async def update_b():
        # Artificial delay to increase overlap risk if not atomic
        await asyncio.sleep(0.01)
        new_leg_b = ArbLeg(
            broker_id="polymarket",
            order=leg_b.order,
            fill_price=Decimal("0.57"),
            fill_quantity=Decimal("10"),
            status="filled",
            external_order_id="ext-b",
        )
        await store.update_leg_atomic(trade.id, "leg_b", new_leg_b)

    # 3. Execute concurrently
    await asyncio.gather(update_a(), update_b())

    # 4. Verify results
    reloaded = await store.get_trade(trade.id)
    assert reloaded.leg_a.status == "filled"
    assert reloaded.leg_a.fill_price == Decimal("0.55")
    assert reloaded.leg_a.external_order_id == "ext-a"

    assert reloaded.leg_b.status == "filled"
    assert reloaded.leg_b.fill_price == Decimal("0.57")
    assert reloaded.leg_b.external_order_id == "ext-b"

    assert reloaded.updated_at > reloaded.created_at
