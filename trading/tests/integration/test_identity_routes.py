import pytest
from fastapi.testclient import TestClient

from api.identity.tokens import generate_token, hash_token


@pytest.fixture
def client_with_master_key():
    from api.app import create_app

    app = create_app()
    client = TestClient(app)
    client.headers["X-API-Key"] = "local-validator-dev"
    return client


@pytest.fixture
def anonymous_client():
    from api.app import create_app

    app = create_app()
    return TestClient(app)


def test_me_endpoint_returns_anonymous_when_no_auth(anonymous_client):
    resp = anonymous_client.get("/api/v1/identity/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "anonymous"


def test_me_endpoint_with_master_key():
    from api.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get(
        "/api/v1/identity/me", headers={"X-API-Key": "local-validator-dev"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "master"
    assert "admin" in data["scopes"]


def test_register_agent_returns_token_once(client_with_master_key):
    resp = client_with_master_key.post(
        "/api/v1/identity/agents",
        json={"name": "test-agent-1", "tier": "verified", "scopes": ["read:arena"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test-agent-1"
    assert data["token"].startswith("amu_")
    assert "warning" in data


def test_register_agent_rejects_duplicate_name(client_with_master_key):
    client_with_master_key.post(
        "/api/v1/identity/agents",
        json={"name": "unique-agent", "tier": "verified"},
    )
    resp = client_with_master_key.post(
        "/api/v1/identity/agents",
        json={"name": "unique-agent", "tier": "verified"},
    )
    assert resp.status_code == 400 or resp.status_code == 500


def test_revoke_agent_requires_admin(anonymous_client):
    resp = anonymous_client.post(
        "/api/v1/identity/agents/some-agent/revoke",
        json={"reason": "test"},
    )
    assert resp.status_code == 403
