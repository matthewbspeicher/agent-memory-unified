import pytest
import aiosqlite
from datetime import datetime, timezone
from decimal import Decimal

from storage.db import init_db
from storage.pnl import TrackedPositionStore
from learning.pnl import TradeTracker
from agents.models import Opportunity, OpportunityStatus
from broker.models import MarketOrder, OrderResult, OrderStatus, OrderSide, Symbol


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        yield conn


@pytest.fixture
async def tracker(db):
    store = TrackedPositionStore(db)
    return TradeTracker(store)


def make_opportunity():
    return Opportunity(
        id="opp-001",
        agent_name="test-agent",
        symbol=Symbol(ticker="AAPL"),
        signal="buy",
        confidence=0.85,
        reasoning="test",
        data={},
        timestamp=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
        status=OpportunityStatus.EXECUTED,
        broker_id="alpaca",
        suggested_trade=MarketOrder(
            symbol=Symbol(ticker="AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            account_id="acct-123",
        ),
    )


def make_order_result(price="150", qty="100", commission="1.25", filled_at=None):
    return OrderResult(
        order_id="ord-001",
        status=OrderStatus.FILLED,
        filled_quantity=Decimal(qty),
        avg_fill_price=Decimal(price),
        commission=Decimal(commission),
        filled_at=filled_at,
    )


@pytest.mark.asyncio
async def test_record_entry_creates_tracked_position(tracker, db):
    opp = make_opportunity()
    result = make_order_result(
        price="150",
        qty="100",
        commission="1.25",
        filled_at=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
    )
    position_id = await tracker.record_entry(opp, result, "buy")

    cursor = await db.execute("SELECT * FROM tracked_positions WHERE id = ?", (position_id,))
    row = dict(await cursor.fetchone())
    assert row["agent_name"] == "test-agent"
    assert row["opportunity_id"] == "opp-001"
    assert row["symbol"] == "AAPL"
    assert row["side"] == "buy"
    assert row["entry_price"] == "150"
    assert row["entry_quantity"] == 100
    assert row["entry_fees"] == "1.25"
    assert row["status"] == "open"
    assert row["broker_id"] == "alpaca"
    assert row["account_id"] == "acct-123"


@pytest.mark.asyncio
async def test_record_exit_closes_position(tracker, db):
    opp = make_opportunity()
    entry_result = make_order_result(
        price="150",
        qty="100",
        commission="1.25",
        filled_at=datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc),
    )
    position_id = await tracker.record_entry(opp, entry_result, "buy")

    exit_result = make_order_result(
        price="155",
        qty="100",
        commission="1.25",
        filled_at=datetime(2026, 3, 25, 14, 0, 0, tzinfo=timezone.utc),
    )
    await tracker.record_exit(position_id, exit_result, "take_profit")

    cursor = await db.execute("SELECT * FROM tracked_positions WHERE id = ?", (position_id,))
    row = dict(await cursor.fetchone())
    assert row["status"] == "closed"
    assert row["exit_price"] == "155"
    assert row["exit_reason"] == "take_profit"


def test_compute_pnl():
    result = TradeTracker.compute_pnl(
        side="buy",
        entry_price=Decimal("150"),
        exit_price=Decimal("155"),
        quantity=Decimal("100"),
        entry_fees=Decimal("1.25"),
        exit_fees=Decimal("1.25"),
    )
    assert result["gross_pnl"] == Decimal("500")
    assert result["net_pnl"] == Decimal("497.50")


def test_compute_pnl_sell_side():
    result = TradeTracker.compute_pnl(
        side="sell",
        entry_price=Decimal("155"),
        exit_price=Decimal("150"),
        quantity=Decimal("100"),
        entry_fees=Decimal("0"),
        exit_fees=Decimal("0"),
    )
    assert result["gross_pnl"] == Decimal("500")
    assert result["net_pnl"] == Decimal("500")
