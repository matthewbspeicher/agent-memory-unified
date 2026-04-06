# tests/unit/test_agents/test_runner.py
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import aiosqlite

from agents.models import (
    ActionLevel,
    AgentConfig,
    AgentStatus,
    Opportunity,
    OpportunityStatus,
)
from agents.runner import AgentRunner
from broker.models import (
    FidelityFeeModel,
    IBKRFeeModel,
    MarketOrder,
    OrderSide,
    Symbol,
    AssetType,
)
from learning.strategy_health import StrategyHealthStatus
from broker.paper import PaperBroker
from storage.paper import PaperStore


def _mock_agent(name="test-agent"):
    cfg = AgentConfig(
        name=name, strategy="rsi", schedule="on_demand", action_level=ActionLevel.NOTIFY
    )
    agent = MagicMock()
    agent.name = name
    agent.config = cfg
    agent.action_level = ActionLevel.NOTIFY
    agent.description = "test"
    agent.setup = AsyncMock()
    agent.teardown = AsyncMock()
    agent.scan = AsyncMock(return_value=[])
    return agent


class TestAgentRunner:
    def test_register_agent(self):
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        agent = _mock_agent()
        runner.register(agent)
        agents = runner.list_agents()
        assert len(agents) == 1
        assert agents[0].name == "test-agent"
        assert agents[0].status == AgentStatus.STOPPED

    async def test_run_once(self):
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        agent = _mock_agent()
        runner.register(agent)
        opps = await runner.run_once("test-agent")
        assert opps == []
        agent.scan.assert_awaited_once()

    async def test_run_once_skips_retired_agent(self):
        health_engine = MagicMock()
        health_engine.get_status = AsyncMock(return_value=StrategyHealthStatus.RETIRED)
        runner = AgentRunner(
            data_bus=MagicMock(),
            router=MagicMock(),
            health_engine=health_engine,
        )
        agent = _mock_agent()
        runner.register(agent)

        opps = await runner.run_once("test-agent")

        assert opps == []
        agent.scan.assert_not_awaited()
        health_engine.get_status.assert_awaited_once_with("test-agent")

    async def test_run_once_unknown_agent(self):
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        with pytest.raises(KeyError):
            await runner.run_once("nonexistent")

    def test_list_agents_empty(self):
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        assert runner.list_agents() == []

    async def test_runner_update_agent_shadow_mode(self):
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        agent = _mock_agent()
        agent.config.shadow_mode = True
        runner.register(agent)

        # Verify shadow_mode is True
        info = runner.get_agent_info("test-agent")
        assert info.config.shadow_mode is True

        # Update to False
        result = await runner.update_agent_shadow_mode("test-agent", shadow_mode=False)
        assert result is True

        # Verify shadow_mode is now False
        info = runner.get_agent_info("test-agent")
        assert info.config.shadow_mode is False

        # Update back to True
        result = await runner.update_agent_shadow_mode("test-agent", shadow_mode=True)
        assert result is True
        info = runner.get_agent_info("test-agent")
        assert info.config.shadow_mode is True

        # Non-existent agent returns False
        result = await runner.update_agent_shadow_mode("nonexistent", shadow_mode=False)
        assert result is False


@pytest.fixture
async def paper_store_memory():
    from tests.unit.test_broker.test_paper import MockBroker

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    store = PaperStore(db)
    await store.init_tables()
    yield store, MockBroker()
    await db.close()


class TestAgentRunnerWithPaperBroker:
    async def test_runner_with_fidelity_paper_broker(self, paper_store_memory):
        store, mock_broker = paper_store_memory
        PaperBroker(mock_broker, store, fee_model=FidelityFeeModel())
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        agent = _mock_agent("fidelity-agent")
        runner.register(agent)

        result = await runner.run_once("fidelity-agent")

        agent.scan.assert_awaited_once()
        assert isinstance(result, list)

    async def test_runner_with_ibkr_paper_broker(self, paper_store_memory):
        store, mock_broker = paper_store_memory
        PaperBroker(mock_broker, store, fee_model=IBKRFeeModel())
        runner = AgentRunner(data_bus=MagicMock(), router=MagicMock())
        agent = _mock_agent("ibkr-agent")
        runner.register(agent)

        result = await runner.run_once("ibkr-agent")

        agent.scan.assert_awaited_once()
        assert isinstance(result, list)

    async def test_runner_run_once_routes_opportunities(self, paper_store_memory):
        store, mock_broker = paper_store_memory
        sym = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
        from datetime import datetime, timezone

        opp = Opportunity(
            id="test-opp-1",
            agent_name="routing-agent",
            symbol=sym,
            signal="buy",
            confidence=0.9,
            reasoning="Test routing",
            data={},
            status=OpportunityStatus.PENDING,
            timestamp=datetime.now(timezone.utc),
            suggested_trade=MarketOrder(
                symbol=sym,
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                account_id="PAPER",
            ),
        )

        router = MagicMock()
        router.route = AsyncMock()
        agent = _mock_agent("routing-agent")
        agent.scan = AsyncMock(return_value=[opp])

        runner = AgentRunner(data_bus=MagicMock(), router=router)
        runner.register(agent)

        result = await runner.run_once("routing-agent")

        assert len(result) == 1
        router.route.assert_awaited_once_with(opp, ActionLevel.NOTIFY)
