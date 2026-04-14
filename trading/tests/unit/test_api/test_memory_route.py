import os
import pytest
from fastapi.testclient import TestClient
from api.app import create_app

AUTH_HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def set_api_key():
    os.environ["STA_API_KEY"] = "test-key"
    from api.auth import _get_settings

    _get_settings.cache_clear()
    yield
    _get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clear_memory_registry():
    from api.services.memory_registry import memory_registry

    memory_registry._clients.clear()
    memory_registry.register_shared(None)


def test_memory_list_returns_503_when_not_configured():
    """When memory system is not configured, endpoint returns 503."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/engine/v1/memory/momentum_agent", headers=AUTH_HEADERS)
    assert response.status_code == 503


def test_market_observations_returns_503_when_not_configured():
    app = create_app()
    client = TestClient(app)
    response = client.get("/engine/v1/memory/market/observations", headers=AUTH_HEADERS)
    assert response.status_code == 503


def test_search_returns_503_when_not_configured():
    app = create_app()
    client = TestClient(app)
    response = client.get(
        "/engine/v1/memory/search?agent=momentum_agent&q=AAPL", headers=AUTH_HEADERS
    )
    assert response.status_code == 503


def test_health_returns_empty_registry_when_not_configured():
    """Preflight succeeds even with no agents — that's a real, valid state."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/engine/v1/memory/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["agent_count"] == 0
    assert body["registered_agents"] == []
    assert body["shared_configured"] is False


def test_health_reports_registered_agents():
    from api.services.memory_registry import memory_registry

    memory_registry.register_client("alice", object())
    memory_registry.register_client("bob", object())
    memory_registry.register_shared(object())

    app = create_app()
    client = TestClient(app)
    response = client.get("/engine/v1/memory/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["agent_count"] == 2
    assert body["registered_agents"] == ["alice", "bob"]
    assert body["shared_configured"] is True


def test_health_runs_local_store_preflight_when_present():
    """If a local store is wired into the registry, preflight runs and is reported."""
    from api.services.memory_registry import memory_registry

    class _StubStore:
        async def _preflight_check(self):
            return {"ok": True, "checks": {"connection": True, "row_count": 7}}

    memory_registry._local_store = _StubStore()

    app = create_app()
    client = TestClient(app)
    response = client.get("/engine/v1/memory/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["local_store"]["ok"] is True
    assert body["local_store"]["checks"]["row_count"] == 7

    delattr(memory_registry, "_local_store")


def test_health_marks_unhealthy_when_local_store_preflight_fails():
    from api.services.memory_registry import memory_registry

    class _BadStore:
        async def _preflight_check(self):
            return {"ok": False, "reason": "missing columns: ['embedding']", "checks": {}}

    memory_registry._local_store = _BadStore()

    app = create_app()
    client = TestClient(app)
    response = client.get("/engine/v1/memory/health", headers=AUTH_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["local_store"]["ok"] is False
    assert "embedding" in body["local_store"]["reason"]

    delattr(memory_registry, "_local_store")
