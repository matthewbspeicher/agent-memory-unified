import pytest
import asyncio
from data.events import EventBus


@pytest.mark.asyncio
async def test_event_bus_pub_sub():
    bus = EventBus()

    received = []

    async def subscriber():
        async for event in bus.subscribe():
            received.append(event)
            if len(received) >= 2:
                break

    sub_task = asyncio.create_task(subscriber())

    # Wait for the generator to be primed and queue added
    await asyncio.sleep(0.05)

    await bus.publish("topic1", {"msg": "hello"})
    await bus.publish("topic2", {"msg": "world"})

    await asyncio.wait_for(sub_task, timeout=1.0)

    assert len(received) == 2
    assert received[0] == {"topic": "topic1", "data": {"msg": "hello"}}
    assert received[1] == {"topic": "topic2", "data": {"msg": "world"}}


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    bus = EventBus()

    async def subscriber(results, expected_count):
        async for event in bus.subscribe():
            results.append(event)
            if len(results) >= expected_count:
                break

    res1 = []
    res2 = []
    t1 = asyncio.create_task(subscriber(res1, 1))
    t2 = asyncio.create_task(subscriber(res2, 1))

    await asyncio.sleep(0.05)

    await bus.publish("broadcast", {"test": "ok"})

    await asyncio.wait_for(t1, timeout=1.0)
    await asyncio.wait_for(t2, timeout=1.0)

    assert len(res1) == 1
    assert len(res2) == 1
    assert res1[0] == res2[0] == {"topic": "broadcast", "data": {"test": "ok"}}
