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
    from api.routes.memory import _memory_client_registry, register_shared_client
    _memory_client_registry.clear()
    register_shared_client(None)


def test_memory_list_returns_503_when_not_configured():
    """When memory system is not configured, endpoint returns 503."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/memory/momentum_agent", headers=AUTH_HEADERS)
    assert response.status_code == 503


def test_market_observations_returns_503_when_not_configured():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/memory/market/observations", headers=AUTH_HEADERS)
    assert response.status_code == 503


def test_search_returns_503_when_not_configured():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/memory/search?agent=momentum_agent&q=AAPL", headers=AUTH_HEADERS)
    assert response.status_code == 503
