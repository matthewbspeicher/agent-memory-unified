import sys
import pytest
import json
from unittest.mock import AsyncMock, MagicMock

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
    from api.routes import drafts as drafts_router

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
    from api.identity.tokens import generate_token, hash_token

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
