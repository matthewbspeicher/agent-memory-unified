# Redis Event Bus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the Redis Streams event publisher to broadcast live Arena events, and the consumer to feed the Bookie market.

**Architecture:** A singleton `EventPublisher` using `redis.asyncio` pushes JSON events to the `arena_live_events` stream. A `BookieConsumer` listens to this stream and updates the `BookieMarket` state.

**Tech Stack:** Python 3.14, `redis.asyncio`, JSON.

---

### Task 1: Redis Event Publisher

**Files:**
- Create: `trading/events/publisher.py`
- Test: `trading/shared/tests/test_event_publisher.py`

- [x] **Step 1: Write the failing test for the publisher**

```python
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/shared/tests/test_event_publisher.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [x] **Step 3: Write minimal implementation**

```python
import json
import redis.asyncio as redis
from typing import Dict, Any, Optional

class EventPublisher:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    async def publish(self, stream_name: str, event_data: Dict[str, Any]) -> str:
        if not self.client:
            await self.connect()
            
        payload = {"payload": json.dumps(event_data)}
        msg_id = await self.client.xadd(stream_name, payload)
        return msg_id
        
    async def close(self):
        if self.client:
            await self.client.close()
```

- [x] **Step 4: Run test to verify it passes**

Run: `export PYTHONPATH=$PYTHONPATH:. && pytest trading/shared/tests/test_event_publisher.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add trading/shared/tests/test_event_publisher.py trading/events/publisher.py
git commit -m "feat: implement Redis Event Publisher"
```

---

### Task 2: Redis Event Consumer

**Files:**
- Create: `trading/events/consumer.py`
- Test: `trading/shared/tests/test_event_consumer.py`

- [x] **Step 1: Write the failing test for the consumer**

```python
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/shared/tests/test_event_consumer.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [x] **Step 3: Write minimal implementation**

```python
import json
import redis.asyncio as redis
from typing import Dict, Any, List, Optional

class EventConsumer:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    async def read_events(self, stream_name: str, group_name: str, consumer_name: str) -> List[Dict[str, Any]]:
        if not self.client:
            await self.connect()
            
        try:
            await self.client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
                
        streams = {stream_name: ">"}
        messages = await self.client.xreadgroup(group_name, consumer_name, streams, count=10, block=100)
        
        parsed_events = []
        for stream, msgs in messages:
            for msg_id, msg_data in msgs:
                if "payload" in msg_data:
                    try:
                        event = json.loads(msg_data["payload"])
                        event["_msg_id"] = msg_id
                        parsed_events.append(event)
                        # Acknowledge the message
                        await self.client.xack(stream_name, group_name, msg_id)
                    except json.JSONDecodeError:
                        pass
                        
        return parsed_events

    async def close(self):
        if self.client:
            await self.client.close()
```

- [x] **Step 4: Run test to verify it passes**

Run: `export PYTHONPATH=$PYTHONPATH:. && pytest trading/shared/tests/test_event_consumer.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add trading/shared/tests/test_event_consumer.py trading/events/consumer.py
git commit -m "feat: implement Redis Event Consumer"
```
