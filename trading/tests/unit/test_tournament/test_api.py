import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from api.routes.tournament import create_tournament_router
from api.auth import verify_api_key


@pytest.fixture
def client():
    engine = MagicMock()
    engine.override = AsyncMock(
        return_value="Override applied: agent1 promoted to stage 2."
    )
    app = FastAPI()
    app.include_router(create_tournament_router(engine))
    app.dependency_overrides[verify_api_key] = lambda: "test-key"

    from api.identity.dependencies import resolve_identity, Identity

    async def _admin_identity():
        return Identity(name="master", scopes=frozenset(["admin", "*"]), tier="admin")

    app.dependency_overrides[resolve_identity] = _admin_identity
    return TestClient(app), engine


def test_override_endpoint_calls_engine(client):
    tc, engine = client
    resp = tc.post(
        "/tournament/override",
        json={"agent_name": "agent1", "action": "promote"},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 200
    assert "promoted" in resp.json()["message"].lower()


def test_override_endpoint_missing_fields_returns_422(client):
    tc, _ = client
    resp = tc.post("/tournament/override", json={}, headers={"X-API-Key": "test-key"})
    assert resp.status_code == 422


def test_get_audit_log_returns_list(client):
    tc, engine = client
    engine.store_list_audit = None
    # Patch the store on the engine
    engine._store = MagicMock()
    engine._store.list_audit = AsyncMock(
        return_value=[
            {
                "id": 1,
                "agent_name": "agent1",
                "from_stage": 0,
                "to_stage": 1,
                "reason": "thresholds passed",
                "ai_analysis": "Looks good",
                "ai_recommendation": "go",
                "timestamp": "2026-03-27T00:00:00",
                "overridden_by": None,
            }
        ]
    )
    resp = tc.get("/tournament/log", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["agent_name"] == "agent1"
