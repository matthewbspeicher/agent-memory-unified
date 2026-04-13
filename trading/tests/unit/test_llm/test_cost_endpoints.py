"""Integration tests for cost ceiling endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


class TestCostStatusEndpoint:
    """Test GET /llm/cost/status endpoint."""

    def test_cost_status_returns_structure(self):
        """Cost status should return budget info and spend breakdown."""
        from api.app import create_app

        app = create_app()
        client = TestClient(app)

        mock_ledger = MagicMock()
        mock_ledger.get_spend_summary = MagicMock(
            return_value={
                "total_spend_cents": 45.0,
                "daily_budget_cents": 100.0,
                "percent_used": 0.45,
                "provider_breakdown": {"anthropic": 30.0, "groq": 15.0},
                "window_reset_at": "2026-04-14T00:00:00Z",
                "agents": {"test-agent": 45.0},
            }
        )
        app.state.cost_ledger = mock_ledger

        resp = client.get("/llm/cost/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_spend_cents" in data
        assert "daily_budget_cents" in data
        assert "percent_used" in data
        assert "provider_breakdown" in data

    def test_cost_status_returns_503_without_ledger(self):
        """Should return 503 if cost_ledger not initialized."""
        from api.app import create_app

        app = create_app()
        client = TestClient(app)

        app.state.cost_ledger = None

        resp = client.get("/llm/cost/status")
        assert resp.status_code == 503


class TestCostAgentEndpoint:
    """Test GET /llm/cost/agent/{agent_name} endpoint."""

    def test_agent_cost_returns_specific_agent(self):
        """Should return spend for specific agent."""
        from api.app import create_app

        app = create_app()
        client = TestClient(app)

        mock_ledger = MagicMock()
        mock_ledger.get_agent_spend = MagicMock(
            return_value={
                "agent_name": "trading-agent",
                "spend_cents": 25.0,
                "call_count": 10,
                "last_call_at": "2026-04-13T15:30:00Z",
            }
        )
        app.state.cost_ledger = mock_ledger

        resp = client.get("/llm/cost/agent/trading-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "trading-agent"
        assert "spend_cents" in data
        assert "call_count" in data
