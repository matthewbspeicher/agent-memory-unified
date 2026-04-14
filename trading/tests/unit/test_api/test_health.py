from unittest.mock import MagicMock


def test_health_connected(client):
    resp = client.get("/health", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "brokers" in data


def test_health_disconnected(client, mock_broker):
    mock_broker.connection.is_connected.return_value = False
    resp = client.get("/health", headers={"X-API-Key": "test-key"})
    data = resp.json()
    assert "brokers" in data
    # At least one broker should show disconnected
    ibkr = data["brokers"].get("ibkr", {})
    assert ibkr.get("connected") is False


class TestHealthServices:
    def test_health_services_includes_trading_engine(self, client):
        resp = client.get("/health/services", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        names = [s["name"] for s in data["services"]]
        assert "trading_engine" in names

    def test_health_services_includes_cached_railway(self, client):
        mock_cache = MagicMock()
        mock_cache.all_statuses.return_value = {
            "railway": {"status": "healthy", "deploy_status": "active"}
        }
        client.app.state.health_cache = mock_cache

        resp = client.get("/health/services", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        railway = next((s for s in data["services"] if s["name"] == "railway"), None)
        assert railway is not None
        assert railway["status"] == "healthy"
        assert railway["deploy_status"] == "active"

    def test_health_services_without_cache_only_returns_engine(self, client):
        # Ensure no health_cache on state
        if hasattr(client.app.state, "health_cache"):
            delattr(client.app.state, "health_cache")

        resp = client.get("/health/services", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        names = [s["name"] for s in data["services"]]
        assert names == ["trading_engine"]
