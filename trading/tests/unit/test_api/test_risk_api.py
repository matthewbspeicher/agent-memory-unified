# tests/unit/test_api/test_risk_api.py
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from risk.kill_switch import KillSwitch
from risk.rules import MaxPositionSize


@pytest.fixture
def risk_client(mock_broker):
    import os

    os.environ["STA_API_KEY"] = "test-key"
    from api.app import create_app
    from api.routes.risk import router as risk_router

    app = create_app(mock_broker)
    app.include_router(risk_router)
    ks = KillSwitch()
    engine = MagicMock()
    engine.kill_switch = ks
    engine.rules = [MaxPositionSize(max_dollars=5000, max_shares=500)]
    app.state.risk_engine = engine
    return TestClient(app)


class TestRiskAPI:
    def test_get_status(self, risk_client):
        resp = risk_client.get("/risk/status", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["kill_switch"] is False
        assert "rules" in data

    def test_enable_kill_switch(self, risk_client):
        resp = risk_client.post(
            "/risk/kill-switch",
            json={"enabled": True},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["kill_switch"] is True

    def test_disable_kill_switch(self, risk_client):
        # Enable first, then disable
        risk_client.post(
            "/risk/kill-switch",
            json={"enabled": True},
            headers={"X-API-Key": "test-key"},
        )
        resp = risk_client.post(
            "/risk/kill-switch",
            json={"enabled": False},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["kill_switch"] is False
