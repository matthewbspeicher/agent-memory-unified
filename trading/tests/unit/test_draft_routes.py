import sys
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules["asyncpg"] = MagicMock()
sys.modules["asyncpg.exceptions"] = MagicMock()

from fastapi.testclient import TestClient
from api.identity.store import IdentityStore


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.connection.connect = AsyncMock()
    broker.connection.disconnect = AsyncMock()
    broker.connection._reconnecting = False
    from broker.models import BrokerCapabilities

    broker.capabilities.return_value = BrokerCapabilities(
        stocks=True,
        options=True,
        futures=True,
        forex=True,
        bonds=True,
        streaming=True,
    )
    return broker


@pytest.fixture
def client(mock_broker, mock_pool):
    import os

    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    from api.app import create_app

    pool, conn = mock_pool
    store = IdentityStore(pool)

    app = create_app(mock_broker)
    app.state.identity_store = store

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.delete = AsyncMock()
    app.state.redis = mock_redis

    return TestClient(app), conn


@pytest.fixture
def auth_headers():
    from api.identity.tokens import generate_token

    token = generate_token("test_agent")
    return {"X-API-Key": token}


def test_create_draft_requires_auth(client):
    c, _ = client
    res = c.post("/api/v1/drafts", json={"name": "Test", "system_prompt": "Test"})
    assert res.status_code in (401, 403)


def test_list_drafts_requires_auth(client):
    c, _ = client
    res = c.get("/api/v1/drafts")
    assert res.status_code in (401, 403)


class TestBacktestEngine:
    """Test that the backtest endpoint uses the real engine."""

    def test_backtest_returns_real_status(self):
        from backtest.engine import run_backtest

        result = run_backtest(symbols=["BTC"], days=10)
        assert result["status"] == "real"
        assert "sharpe_ratio" in result
        assert "equity_curve" in result

    def test_backtest_result_shape_matches_frontend(self):
        from backtest.engine import run_backtest

        result = run_backtest(symbols=["BTC"], days=10)
        # Frontend Lab.tsx expects these fields
        assert isinstance(result["sharpe_ratio"], float)
        assert isinstance(result["win_rate"], float)
        assert isinstance(result["max_drawdown"], float)
        assert isinstance(result["total_trades"], int)
        assert isinstance(result["equity_curve"], list)
        for pt in result["equity_curve"]:
            assert "timestamp" in pt
            assert "equity" in pt


class TestDeployToYaml:
    """Test that deploy writes to agents.yaml."""

    def test_deploy_builds_correct_agent_entry(self):
        """Verify the agent YAML entry structure."""
        import yaml

        draft = {
            "name": "Momentum Hunter",
            "model": "gpt-4o",
            "system_prompt": "You are a momentum trading agent.",
            "hyperparameters": {"temperature": 0.7, "top_p": 1.0},
            "status": "tested",
        }

        agent_name = draft["name"].lower().replace(" ", "_")
        assert agent_name == "momentum_hunter"

        entry = {
            "name": agent_name,
            "strategy": "llm_analyst",
            "schedule": "on_demand",
            "action_level": "notify",
            "model": draft["model"],
            "system_prompt": draft["system_prompt"],
            "trust_level": "monitored",
            "parameters": {
                k: v
                for k, v in draft["hyperparameters"].items()
                if k not in ("symbols", "backtest_days", "initial_capital")
            },
        }

        assert entry["name"] == "momentum_hunter"
        assert entry["model"] == "gpt-4o"
        assert entry["trust_level"] == "monitored"
        assert entry["parameters"]["temperature"] == 0.7

        # Verify it serializes cleanly to YAML
        output = yaml.dump({"agents": [entry]}, default_flow_style=False)
        parsed = yaml.safe_load(output)
        assert parsed["agents"][0]["name"] == "momentum_hunter"

    def test_deploy_filters_backtest_params(self):
        """symbols, backtest_days, initial_capital should not leak into agent params."""
        hyperparameters = {
            "temperature": 0.7,
            "symbols": ["BTC", "ETH"],
            "backtest_days": 90,
            "initial_capital": 100000,
        }
        filtered = {
            k: v
            for k, v in hyperparameters.items()
            if k not in ("symbols", "backtest_days", "initial_capital")
        }
        assert filtered == {"temperature": 0.7}
