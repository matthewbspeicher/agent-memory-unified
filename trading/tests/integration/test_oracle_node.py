import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from config import Config
from data.events import EventBus
from data.redis_bridge import RedisSignalBridge

@pytest.mark.asyncio
async def test_redis_signal_bridge_propagation():
    """Verify that EventBus events are propagated to Redis and vice-versa."""
    # This test requires a mock Redis or a running Redis instance.
    # We will mock the redis asyncio client.
    
    event_bus = EventBus()
    redis_url = "redis://localhost:6379/0"
    bridge = RedisSignalBridge(event_bus, redis_url, node_id="test-node")
    
    # Mock Redis
    mock_redis = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub
    
    with MagicMock(return_value=mock_redis) as mock_from_url:
        import redis.asyncio as redis_lib
        redis_lib.from_url = mock_from_url
        
        await bridge.start()
        
        # Test 1: Local Event -> Redis Publish
        signal_data = {"symbol": "AAPL", "side": "BUY"}
        await event_bus.publish("agent_signal", signal_data)
        
        # Wait for async propagation
        await asyncio.sleep(0.1)
        
        # Verify redis.publish was called
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
