import pytest
from datetime import datetime, timezone
import aiosqlite

from storage.db import init_db
from storage.performance import PerformanceStore
from storage.opportunities import OpportunityStore
from agents.runner import AgentRunner
from agents.analytics import AnalyticsAgent
from agents.models import AgentConfig
from data.bus import DataBus
from agents.router import OpportunityRouter
from broker.paper import PaperBroker
from notifications.log_notifier import LogNotifier


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    # Create tables needed by this test (init_db is a no-op since Laravel owns DDL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal TEXT NOT NULL,
            confidence REAL NOT NULL,
            reasoning TEXT NOT NULL,
            suggested_trade TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            expires_at TEXT,
            data TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await conn.commit()
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_analytics_agent(db):
    # Setup dependencies
    opp_store = OpportunityStore(db)
    perf_store = PerformanceStore(db)
    from tests.unit.test_broker.test_paper import MockBroker
    from storage.paper import PaperStore

    broker = PaperBroker(MockBroker(), PaperStore(db))
    await broker._store.init_tables()
    data_bus = DataBus()
    router = OpportunityRouter(opp_store, LogNotifier(), None, broker, None, data_bus)
    runner = AgentRunner(data_bus, router)

    # Register a dummy agent to be analyzed
    from agents.base import Agent

    class DummyAgent(Agent):
        @property
        def description(self):
            return "dummy"

        async def setup(self):
            pass

        async def teardown(self):
            pass

        async def scan(self, bus):
            return []

    from agents.models import ActionLevel

    runner.register(
        DummyAgent(
            AgentConfig(
                name="DummyAgent",
                strategy="dummy",
                schedule="continuous",
                action_level=ActionLevel.NOTIFY,
            )
        )
    )

    # Insert some mock opportunities for DummyAgent so win_rate can be calc'd
    from agents.models import Opportunity, OpportunityStatus, ActionLevel

    from broker.models import Symbol, AssetType

    opp = Opportunity(
        id="opp1",
        agent_name="DummyAgent",
        symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
        signal="buy",
        confidence=0.9,
        reasoning="Test",
        data={},
        status=OpportunityStatus.EXECUTED,
        timestamp=datetime.now(timezone.utc),
    )
    await opp_store.save(opp)

    opp2 = Opportunity(
        id="opp2",
        agent_name="DummyAgent",
        symbol=Symbol(ticker="GOOG", asset_type=AssetType.STOCK),
        signal="buy",
        confidence=0.8,
        reasoning="Test 2",
        data={},
        status=OpportunityStatus.REJECTED,
        timestamp=datetime.now(timezone.utc),
    )
    await opp_store.save(opp2)

    # Run the AnalyticsAgent with constructor-injected dependencies
    from storage.trades import TradeStore

    analytics = AnalyticsAgent(
        AgentConfig(
            name="AnalyticsAgent",
            strategy="analytics",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
        ),
        runner=runner,
        opp_store=opp_store,
        perf_store=perf_store,
        trade_store=TradeStore(db),
    )
    await analytics.scan(data_bus)

    # Verify PerformanceStore has a snapshot
    history = await perf_store.get_history("DummyAgent")
    assert len(history) == 1
    assert history[0].opportunities_generated == 2
    assert history[0].opportunities_executed == 1
    # win_rate = 1 executed / (1 executed + 1 rejected) = 0.5
    assert history[0].win_rate == 0.5


async def _setup_analytics_env(db):
    """Helper that wires up runner + analytics agent for the given db."""
    from agents.analytics import AnalyticsAgent
    from agents.base import Agent
    from agents.models import ActionLevel, AgentConfig
    from agents.router import OpportunityRouter
    from broker.paper import PaperBroker
    from data.bus import DataBus
    from notifications.log_notifier import LogNotifier
    from storage.opportunities import OpportunityStore
    from storage.paper import PaperStore
    from storage.performance import PerformanceStore
    from storage.trades import TradeStore
    from tests.unit.test_broker.test_paper import MockBroker

    opp_store = OpportunityStore(db)
    perf_store = PerformanceStore(db)
    trade_store = TradeStore(db)
    broker = PaperBroker(MockBroker(), PaperStore(db))
    await broker._store.init_tables()
    data_bus = DataBus()
    router = OpportunityRouter(opp_store, LogNotifier(), None, broker, None, data_bus)
    runner = AgentRunner(data_bus, router)

    class DummyAgent(Agent):
        @property
        def description(self):
            return "dummy"

        async def setup(self):
            pass

        async def teardown(self):
            pass

        async def scan(self, bus):
            return []

    runner.register(
        DummyAgent(
            AgentConfig(
                name="TradeAgent",
                strategy="dummy",
                schedule="continuous",
                action_level=ActionLevel.NOTIFY,
            )
        )
    )

    analytics = AnalyticsAgent(
        AgentConfig(
            name="AnalyticsAgent",
            strategy="analytics",
            schedule="continuous",
            action_level=ActionLevel.NOTIFY,
        ),
        runner=runner,
        opp_store=opp_store,
        perf_store=perf_store,
        trade_store=trade_store,
    )
    return analytics, perf_store, trade_store, data_bus


@pytest.mark.asyncio
async def test_analytics_sharpe_ratio_computed(db):
    analytics, perf_store, trade_store, data_bus = await _setup_analytics_env(db)

    # Insert 5 sell trades for "TradeAgent" with varying P&L to produce non-zero returns
    sell_prices = [110.0, 105.0, 115.0, 108.0, 120.0]
    for i, price in enumerate(sell_prices):
        order_result = {
            "order_id": f"ord-{i}",
            "status": "FILLED",
            "avg_fill_price": str(price),
            "filled_quantity": "10",
            "side": "SELL",
            "commission": "0",
        }
        await trade_store.save_trade(
            opportunity_id=f"opp-sharpe-{i}",
            order_result=order_result,
            agent_name="TradeAgent",
        )

    await analytics.scan(data_bus)

    history = await perf_store.get_history("TradeAgent")
    assert len(history) == 1
    assert history[0].sharpe_ratio != 0.0


@pytest.mark.asyncio
async def test_analytics_max_drawdown_computed(db):
    analytics, perf_store, trade_store, data_bus = await _setup_analytics_env(db)

    # Simulate a drawdown: gains then a big loss then recovery
    # SELL trades: price * qty = gross P&L for sells
    # Pattern: 100, 200, -500, 100, 100  (achieved via price * qty for sells)
    # We encode this as sell prices that translate to those gross values at qty=1
    sell_pnl_pattern = [100.0, 200.0, -500.0, 100.0, 100.0]
    for i, pnl in enumerate(sell_pnl_pattern):
        # For a SELL: pnl = price * qty  → price = pnl (qty=1)
        # Negative pnl = represent as a BUY (cash outflow)
        if pnl >= 0:
            order_result = {
                "order_id": f"ord-dd-{i}",
                "status": "FILLED",
                "avg_fill_price": str(pnl),
                "filled_quantity": "1",
                "side": "SELL",
                "commission": "0",
            }
        else:
            order_result = {
                "order_id": f"ord-dd-{i}",
                "status": "FILLED",
                "avg_fill_price": str(abs(pnl)),
                "filled_quantity": "1",
                "side": "BUY",
                "commission": "0",
            }
        await trade_store.save_trade(
            opportunity_id=f"opp-dd-{i}",
            order_result=order_result,
            agent_name="TradeAgent",
        )

    await analytics.scan(data_bus)

    history = await perf_store.get_history("TradeAgent")
    assert len(history) == 1
    assert history[0].max_drawdown > 0.0
