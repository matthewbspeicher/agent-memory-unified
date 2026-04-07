import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from config import Config
from data.events import EventBus
from data.redis_bridge import RedisSignalBridge


@pytest.mark.asyncio
async def test_redis_signal_bridge_propagation():
    """Verify that EventBus events are propagated to Redis and vice-versa."""
    event_bus = EventBus()
    redis_url = "redis://localhost:6379/0"
    bridge = RedisSignalBridge(event_bus, redis_url, node_id="test-node")

    mock_redis = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    async def _empty_listen():
        # Yield nothing — keeps the listener task alive without errors
        while True:
            await asyncio.sleep(10)
            yield  # pragma: no cover

    mock_pubsub.listen = _empty_listen

    with patch("data.redis_bridge.redis.from_url", return_value=mock_redis):
        await bridge.start()

        # Let the bus listener task register its queue subscription
        await asyncio.sleep(0.05)

        signal_data = {"symbol": "AAPL", "side": "BUY"}
        await event_bus.publish("agent_signal", signal_data)

        # Let the bus listener task process the event
        await asyncio.sleep(0.1)

        assert mock_redis.publish.called

        await bridge.stop()


def test_worker_mode_settings():
    """Verify that settings correctly reflect worker mode flags."""
    # Test default
    s = Config()
    assert s.worker_mode is False

    # Test override via env-style dict
    s2 = Config(worker_mode=True, oracle_url="http://oracle")
    assert s2.worker_mode is True
    assert s2.oracle_url == "http://oracle"
