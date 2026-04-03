from datetime import datetime, timezone
from decimal import Decimal
import json
import aiosqlite
import pytest

from agents.models import Opportunity, OpportunityStatus
from broker.models import MarketOrder, OrderSide, Symbol
from storage.db import init_db
from storage.opportunities import OpportunityStore


@pytest.fixture
async def store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield OpportunityStore(db)
    await db.close()


def _opp(id="test-1", ticker="AAPL", signal="RSI_OVERSOLD"):
    return Opportunity(
        id=id, agent_name="test-agent", symbol=Symbol(ticker=ticker),
        signal=signal, confidence=0.85, reasoning="Test",
        data={"rsi": 25.0}, timestamp=datetime.now(timezone.utc),
    )


class TestOpportunityStore:
    async def test_save_and_get(self, store):
        opp = _opp()
        await store.save(opp)
        result = await store.get(opp.id)
        assert result is not None
        assert result["id"] == "test-1"
        assert result["signal"] == "RSI_OVERSOLD"

    async def test_get_missing_returns_none(self, store):
        result = await store.get("nonexistent")
        assert result is None

    async def test_list_by_agent(self, store):
        await store.save(_opp(id="1"))
        await store.save(_opp(id="2"))
        results = await store.list(agent_name="test-agent")
        assert len(results) == 2

    async def test_list_by_symbol(self, store):
        await store.save(_opp(id="1", ticker="AAPL"))
        await store.save(_opp(id="2", ticker="MSFT"))
        results = await store.list(symbol="AAPL")
        assert len(results) == 1

    async def test_update_status(self, store):
        await store.save(_opp())
        await store.update_status("test-1", OpportunityStatus.APPROVED)
        result = await store.get("test-1")
        assert result["status"] == "approved"

    async def test_list_with_limit(self, store):
        for i in range(5):
            await store.save(_opp(id=f"opp-{i}"))
        results = await store.list(limit=3)
        assert len(results) == 3

    async def test_save_preserves_suggested_trade(self, store):
        trade = MarketOrder(
            symbol=Symbol(ticker="AAPL"),
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            account_id="test-account",
        )
        opp = Opportunity(
            id="test-st", agent_name="test-agent", symbol=Symbol(ticker="AAPL"),
            signal="RSI_OVERSOLD", confidence=0.9, reasoning="Test",
            data={}, timestamp=datetime.now(timezone.utc), suggested_trade=trade,
        )
        await store.save(opp)
        result = await store.get(opp.id)
        assert result is not None
        parsed = json.loads(result["suggested_trade"])
        assert parsed["side"] == "BUY"
        assert parsed["quantity"] == "100"
