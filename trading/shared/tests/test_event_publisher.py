import pytest
from unittest.mock import AsyncMock, patch
from trading.events.publisher import EventPublisher

@pytest.mark.asyncio
async def test_publish_event():
    with patch('trading.events.publisher.redis.Redis') as MockRedis:
        mock_client = AsyncMock()
        MockRedis.from_url.return_value = mock_client
        
        publisher = EventPublisher(redis_url="redis://localhost")
        await publisher.connect()
        
        await publisher.publish("arena_live_events", {"event_type": "test_event"})
        
        mock_client.xadd.assert_called_once()
        args, kwargs = mock_client.xadd.call_args
        assert args[0] == "arena_live_events"
        assert "event_type" in args[1]["payload"]