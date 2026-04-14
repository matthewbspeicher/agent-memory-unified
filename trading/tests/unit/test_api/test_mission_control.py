"""Tests for the Mission Control aggregation endpoint."""

from unittest.mock import AsyncMock, MagicMock


def test_mission_control_status_without_auth_returns_401(client):
    resp = client.get("/engine/v1/mission-control/status")
    assert resp.status_code in (401, 403)


def test_mission_control_status_returns_structure(client):
    resp = client.get(
        "/engine/v1/mission-control/status", headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "kpis" in data
    assert "infra" in data
    assert "agents" in data
    assert "activity" in data
    assert "trades" in data
    assert "validator" in data


def test_mission_control_kpis_shape(client):
    resp = client.get(
        "/engine/v1/mission-control/status", headers={"X-API-Key": "test-key"}
    )
    data = resp.json()
    kpis = data["kpis"]
    assert "system_status" in kpis
    assert "agents_active" in kpis
    assert "agents_total" in kpis
    assert "open_trades" in kpis
    assert "unrealized_pnl" in kpis
    assert "validator_enabled" in kpis


def test_mission_control_infra_includes_trading_engine(client):
    resp = client.get(
        "/engine/v1/mission-control/status", headers={"X-API-Key": "test-key"}
    )
    infra = resp.json()["infra"]
    names = [s["name"] for s in infra["services"]]
    assert "trading_engine" in names


def test_mission_control_aggregates_open_trades(client):
    mock_store = MagicMock()
    mock_store.list_open = AsyncMock(
        return_value=[
            {
                "symbol": "AAPL",
                "side": "long",
                "quantity": 100,
                "entry_price": 220.0,
                "unrealized_pnl": 50.25,
                "agent_name": "rsi_scanner",
            },
        ]
    )
    client.app.state.pnl_store = mock_store

    resp = client.get(
        "/engine/v1/mission-control/status", headers={"X-API-Key": "test-key"}
    )
    data = resp.json()
    assert data["trades"]["count"] == 1
    assert data["trades"]["unrealized_pnl"] == 50.25
    assert data["trades"]["positions"][0]["symbol"] == "AAPL"
    assert data["kpis"]["open_trades"] == 1


def test_mission_control_handles_failing_store(client):
    """Endpoint returns empty result rather than 500 when a store fails."""
    mock_store = MagicMock()
    mock_store.list_open = AsyncMock(side_effect=RuntimeError("db down"))
    client.app.state.pnl_store = mock_store

    resp = client.get(
        "/engine/v1/mission-control/status", headers={"X-API-Key": "test-key"}
    )
    assert resp.status_code == 200
    assert resp.json()["trades"]["count"] == 0
