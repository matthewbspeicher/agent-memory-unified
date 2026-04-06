from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from api.app import create_app
from config import Config
from api.deps import get_agent_runner
from agents.runner import AgentRunner
from agents.models import AgentConfig, ActionLevel
from storage.performance import PerformanceSnapshot
from datetime import datetime, timezone


def test_get_performance(monkeypatch):
    import os

    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()

    settings = Config(broker_mode="paper", api_key="test-key")
    app = create_app(enable_agent_framework=False, config=settings)

    # Set up a mock db on app state
    mock_db = MagicMock()
    app.state.db = mock_db

    client = TestClient(app)

    # Mock runner to return AgentInfo
    runner = AgentRunner(None, None)
    from agents.base import Agent

    class Dummy(Agent):
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
        Dummy(
            AgentConfig(
                name="DummyAgent",
                strategy="dummy",
                schedule="continuous",
                action_level=ActionLevel.NOTIFY,
            )
        )
    )

    app.dependency_overrides[get_agent_runner] = lambda: runner

    # Mock PerformanceStore
    class MockPerformanceStore:
        def __init__(self, db):
            pass

        async def get_history(self, name, limit):
            return [
                PerformanceSnapshot(
                    id=1,
                    agent_name="DummyAgent",
                    timestamp=datetime.now(timezone.utc),
                    opportunities_generated=10,
                    opportunities_executed=5,
                    win_rate=0.5,
                )
            ]

    monkeypatch.setattr("api.routes.analytics.PerformanceStore", MockPerformanceStore)

    auth = {"X-API-Key": "test-key"}

    # Request
    response = client.get("/analytics/agents/DummyAgent/performance", headers=auth)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "DummyAgent"
    assert data[0]["win_rate"] == 0.5

    # Test 404
    response = client.get("/analytics/agents/Unknown/performance", headers=auth)
    assert response.status_code == 404
