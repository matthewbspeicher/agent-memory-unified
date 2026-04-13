import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from api.identity.dependencies import (
    resolve_identity,
    require_scope,
    Identity,
    ANONYMOUS_IDENTITY,
)
from api.identity.tokens import generate_token, hash_token
from api.identity.store import IdentityStore


@pytest.fixture
def mock_store():
    class MockStore:
        def __init__(self):
            self.agents = []

        async def list_active(self):
            return self.agents

        async def create(self, **kwargs):
            from api.identity.store import AgentRecord
            from datetime import datetime

            record = AgentRecord(
                id="test-id",
                name=kwargs["name"],
                token_hash=kwargs["token_hash"],
                scopes=kwargs["scopes"],
                tier=kwargs["tier"],
                created_at=datetime.now(),
                revoked_at=None,
                contact_email=kwargs.get("contact_email"),
                moltbook_handle=kwargs.get("moltbook_handle"),
                metadata={},
            )
            self.agents.append(record)
            return record

    return MockStore()


def test_resolve_identity_anonymous():
    app = FastAPI()
    app.state.identity_store = None
    app.state.config = type("Config", (), {"api_key": "test-key"})()

    @app.get("/test")
    async def test_route(identity: Identity = Depends(resolve_identity)):
        return {"name": identity.name, "tier": identity.tier}

    client = TestClient(app)
    resp = client.get("/test")
    assert resp.status_code == 200
    assert resp.json()["name"] == "anonymous"
    assert resp.json()["tier"] == "anonymous"


def test_require_scope_rejects_anonymous():
    app = FastAPI()
    app.state.identity_store = None
    app.state.config = type("Config", (), {"api_key": "test-key"})()

    @app.get("/protected")
    async def protected(identity: Identity = Depends(require_scope("write:orders"))):
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 403
    assert "write:orders" in resp.json()["detail"]


def test_require_scope_accepts_master_key():
    app = FastAPI()
    app.state.identity_store = None
    app.state.config = type("Config", (), {"api_key": "test-key"})()

    @app.get("/protected")
    async def protected(identity: Identity = Depends(require_scope("write:orders"))):
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/protected", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
