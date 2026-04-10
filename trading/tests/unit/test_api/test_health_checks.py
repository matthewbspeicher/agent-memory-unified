"""Tests for enhanced health check endpoints (TP-010).

Covers: /health-internal (Redis, TaoshiBridge, SignalBus fields),
        /ready (readiness probe with dependency checks).
"""

from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# /health-internal — new dependency fields
# ---------------------------------------------------------------------------


class TestHealthInternalRedis:
    def test_redis_ok(self, client):
        """When Redis is configured and responds to ping, redis.ok is True."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        client.app.state.redis = mock_redis

        resp = client.get("/health-internal")
        assert resp.status_code == 200
        data = resp.json()
        assert data["redis"]["ok"] is True

    def test_redis_not_configured(self, client):
        """When Redis is not set on app.state, redis.ok is None."""
        # Ensure no redis attr
        if hasattr(client.app.state, "redis"):
            delattr(client.app.state, "redis")

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["redis"]["ok"] is None

    def test_redis_ping_fails(self, client):
        """When Redis ping raises, redis.ok is False."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))
        client.app.state.redis = mock_redis

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["redis"]["ok"] is False
        assert "refused" in data["redis"]["detail"]


class TestHealthInternalBridge:
    def test_bridge_running_fresh(self, client):
        """Running bridge with recent scan → ok=True, stale=False."""
        bridge = MagicMock()
        bridge.get_status.return_value = {
            "running": True,
            "last_scan_at": datetime.now(timezone.utc).isoformat(),
        }
        client.app.state.taoshi_bridge = bridge

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["taoshi_bridge"]["ok"] is True
        assert data["taoshi_bridge"]["stale"] is False

    def test_bridge_stale(self, client):
        """Running bridge whose last scan is >120s ago → ok=False, stale=True."""
        bridge = MagicMock()
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        bridge.get_status.return_value = {
            "running": True,
            "last_scan_at": old_time,
        }
        client.app.state.taoshi_bridge = bridge

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["taoshi_bridge"]["ok"] is False
        assert data["taoshi_bridge"]["stale"] is True

    def test_bridge_not_configured(self, client):
        """No bridge → ok=None."""
        if hasattr(client.app.state, "taoshi_bridge"):
            delattr(client.app.state, "taoshi_bridge")

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["taoshi_bridge"]["ok"] is None


class TestHealthInternalSignalBus:
    def test_signal_bus_present(self, client):
        """SignalBus on app.state → ok=True with counts."""
        bus = MagicMock()
        bus._subscribers = [MagicMock(), MagicMock()]
        bus._signals = [MagicMock()]
        client.app.state.signal_bus = bus

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["signal_bus"]["ok"] is True
        assert data["signal_bus"]["subscriber_count"] == 2
        assert data["signal_bus"]["signal_count"] == 1

    def test_signal_bus_not_configured(self, client):
        if hasattr(client.app.state, "signal_bus"):
            delattr(client.app.state, "signal_bus")

        resp = client.get("/health-internal")
        data = resp.json()
        assert data["signal_bus"]["ok"] is None


# ---------------------------------------------------------------------------
# /ready — readiness probe
# ---------------------------------------------------------------------------


class TestReadyEndpoint:
    def test_ready_all_healthy(self, client):
        """All deps up → 200 + ready=True."""
        # Redis OK
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        client.app.state.redis = mock_redis

        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    def test_ready_redis_down(self, client):
        """Redis failing → 503 + ready=False."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("down"))
        client.app.state.redis = mock_redis

        resp = client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["redis"] is False

    def test_ready_db_down(self, client):
        """DB failing → 503 + ready=False."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))
        client.app.state.db = mock_db

        # Redis not configured (None → passes)
        if hasattr(client.app.state, "redis"):
            delattr(client.app.state, "redis")

        resp = client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["db"] is False

    def test_ready_no_deps_configured(self, client):
        """No deps configured (all None) → 200 (nothing to fail)."""
        for attr in ("redis", "db", "brokers"):
            if hasattr(client.app.state, attr):
                delattr(client.app.state, attr)

        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True
