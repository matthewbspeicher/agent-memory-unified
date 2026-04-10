import pytest
from unittest.mock import AsyncMock, patch
from trading.events.consumer import EventConsumer

@pytest.mark.asyncio
async def test_consume_events():
    with patch('trading.events.consumer.redis.Redis') as MockRedis:
        mock_client = AsyncMock()
        mock_client.xreadgroup.return_value = [
            ["arena_live_events", [("1620000000000-0", {"payload": '{"event_type": "test_event"}'})]]
        ]
        MockRedis.from_url.return_value = mock_client
        
        consumer = EventConsumer(redis_url="redis://localhost")
        await consumer.connect()
        
        events = await consumer.read_events("arena_live_events", "group1", "consumer1")
        assert len(events) == 1
        assert events[0]["event_type"] == "test_event"
        
        mock_client.xack.assert_called_once()
