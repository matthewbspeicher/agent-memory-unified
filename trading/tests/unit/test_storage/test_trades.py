import aiosqlite
import pytest

from storage.db import init_db
from storage.trades import TradeStore


@pytest.fixture
async def trade_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield TradeStore(db)
    await db.close()


class TestTradeStore:
    async def test_save_and_get(self, trade_store):
        await trade_store.save_trade(
            "opp-1", {"order_id": "ORD1", "status": "FILLED"}, {"passed": True}
        )
        trades = await trade_store.get_trades("opp-1")
        assert len(trades) == 1
        assert trades[0]["opportunity_id"] == "opp-1"

    async def test_get_trades_empty(self, trade_store):
        trades = await trade_store.get_trades("nonexistent")
        assert trades == []

    async def test_get_all_trades(self, trade_store):
        await trade_store.save_trade("opp-1", {"order_id": "ORD1"})
        await trade_store.save_trade("opp-2", {"order_id": "ORD2"})
        trades = await trade_store.get_trades(limit=10)
        assert len(trades) == 2

    async def test_save_and_get_risk_event(self, trade_store):
        await trade_store.save_risk_event(
            "kill_switch_enabled", {"reason": "daily loss"}
        )
        events = await trade_store.get_risk_events(limit=10)
        assert len(events) == 1
        assert events[0]["event_type"] == "kill_switch_enabled"

    async def test_save_trade_with_agent_name(self, trade_store):
        await trade_store.save_trade(
            "opp-1", {"order_id": "ORD1"}, agent_name="rsi_scanner"
        )
        trades = await trade_store.get_trades("opp-1")
        assert len(trades) == 1
        assert trades[0]["agent_name"] == "rsi_scanner"
