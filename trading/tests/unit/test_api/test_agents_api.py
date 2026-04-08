# tests/unit/test_api/test_agents_api.py
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from agents.models import ActionLevel, AgentConfig, AgentInfo, AgentStatus


@pytest.fixture
def agent_client(mock_broker):
    """Builds a test app WITH the agents router so routes are reachable."""
    import os

    os.environ["STA_API_KEY"] = "test-key"
    from api.app import create_app
    from api.routes.agents import router as agents_router

    app = create_app(mock_broker)
    app.include_router(agents_router)

    runner = MagicMock()
    runner.list_agents.return_value = [
        AgentInfo(
            name="test-agent",
            description="Test",
            status=AgentStatus.STOPPED,
            config=AgentConfig(
                name="test-agent",
                strategy="rsi",
                schedule="on_demand",
                action_level=ActionLevel.NOTIFY,
            ),
        ),
    ]
    runner.get_agent_info.return_value = AgentInfo(
        name="test-agent",
        description="Test",
        status=AgentStatus.STOPPED,
        config=AgentConfig(
            name="test-agent",
            strategy="rsi",
            schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
        ),
    )
    runner.start_agent = AsyncMock()
    runner.stop_agent = AsyncMock()
    runner.run_once = AsyncMock(return_value=[])
    runner._agents = {"test-agent": MagicMock()}
    app.state.agent_runner = runner
    return TestClient(app)


class TestAgentsAPI:
    def test_list_agents(self, agent_client):
        resp = agent_client.get("/agents", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-agent"

    def test_get_agent(self, agent_client):
        resp = agent_client.get("/agents/test-agent", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-agent"

    def test_start_agent(self, agent_client):
        resp = agent_client.post(
            "/agents/test-agent/start", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200

    def test_stop_agent(self, agent_client):
        resp = agent_client.post(
            "/agents/test-agent/stop", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200

    def test_scan_agent(self, agent_client):
        resp = agent_client.post(
            "/agents/test-agent/scan", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestStrategiesEndpoint:
    def test_list_strategies_returns_available(self, agent_client):
        """GET /agents/strategies returns list of strategies with parameter schemas."""
        response = agent_client.get(
            "/agents/strategies",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        strategies = response.json()
        assert isinstance(strategies, list)
        assert len(strategies) > 0

        # Check structure: each strategy has name and parameter_schema
        for s in strategies:
            assert "name" in s
            assert "parameter_schema" in s
            assert isinstance(s["parameter_schema"], dict)

    def test_rsi_strategy_has_parameter_schema(self, agent_client):
        """RSI strategy should expose its parameter schema."""
        response = agent_client.get(
            "/agents/strategies",
            headers={"X-API-Key": "test-key"},
        )
        strategies = {s["name"]: s for s in response.json()}
        assert "rsi" in strategies
        rsi_schema = strategies["rsi"]["parameter_schema"]
        assert "period" in rsi_schema
        assert "oversold" in rsi_schema
        assert "overbought" in rsi_schema
