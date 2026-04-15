# tests/unit/test_api/test_opportunities_api.py
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from models.user import User, PlatformTier


@pytest.fixture
def opp_client(mock_broker):
    import os

    os.environ["STA_API_KEY"] = "test-key"
    from api.app import create_app
    from api.auth import _get_settings
    from api.auth.users import get_current_user
    from api.routes.opportunities import router as opp_router

    _get_settings.cache_clear()
    app = create_app(mock_broker)
    app.include_router(opp_router)

    test_user = User(email="test@example.com", tier=PlatformTier.TRADER)
    app.dependency_overrides[get_current_user] = lambda: test_user

    store = MagicMock()
    store.list = AsyncMock(
        return_value=[
            {
                "id": "opp-1",
                "agent_name": "rsi",
                "symbol": "AAPL",
                "signal": "RSI_OVERSOLD",
                "confidence": 0.85,
                "reasoning": "Test",
                "status": "pending",
                "data": "{}",
                "created_at": "2026-03-25",
            },
        ]
    )
    store.get = AsyncMock(
        return_value={
            "id": "opp-1",
            "agent_name": "rsi",
            "symbol": "AAPL",
            "signal": "RSI_OVERSOLD",
            "confidence": 0.85,
            "reasoning": "Test",
            "status": "pending",
            "data": "{}",
            "created_at": "2026-03-25",
        }
    )
    store.update_status = AsyncMock()
    app.state.opportunity_store = store
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestOpportunitiesAPI:
    def test_list_opportunities(self, opp_client):
        resp = opp_client.get("/opportunities", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_opportunity(self, opp_client):
        resp = opp_client.get("/opportunities/opp-1", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "opp-1"

    def test_get_missing_opportunity(self, opp_client):
        opp_client.app.state.opportunity_store.get = AsyncMock(return_value=None)
        resp = opp_client.get(
            "/opportunities/missing", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 404

    def test_approve_opportunity(self, opp_client):
        resp = opp_client.post(
            "/opportunities/opp-1/approve-auth", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200

    def test_reject_opportunity(self, opp_client):
        resp = opp_client.post(
            "/opportunities/opp-1/reject-auth", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
