import asyncio
import time
import pytest
from adapters.polymarket.data_source import ThreadSafeQuoteCache


@pytest.mark.asyncio
async def test_cache_hit():
    cache = ThreadSafeQuoteCache()
    await cache.update("test_id", 50)
    price = await cache.get("test_id")
    assert price == 50


@pytest.mark.asyncio
async def test_cache_miss():
    cache = ThreadSafeQuoteCache()
    price = await cache.get("non_existent")
    assert price is None


@pytest.mark.asyncio
async def test_cache_staleness():
    cache = ThreadSafeQuoteCache()
    await cache.update("test_id", 50)
    
    # Test with very short max_age
    price = await cache.get("test_id", max_age=0.0001)
    await asyncio.sleep(0.001)
    price = await cache.get("test_id", max_age=0.0001)
    assert price is None


@pytest.mark.asyncio
async def test_thread_safety():
    cache = ThreadSafeQuoteCache()
    
    async def updater(cid, start_val):
        for i in range(100):
            await cache.update(cid, start_val + i)
            await asyncio.sleep(0)

    # Run multiple updaters concurrently
    tasks = [
        updater("id1", 0),
        updater("id1", 1000),
        updater("id2", 5000)
    ]
    await asyncio.gather(*tasks)
    
    price1 = await cache.get("id1")
    price2 = await cache.get("id2")
    
    assert price1 is not None
    assert price2 is not None
    assert 1000 <= price1 < 1100 or 0 <= price1 < 100
    assert 5000 <= price2 < 5100
