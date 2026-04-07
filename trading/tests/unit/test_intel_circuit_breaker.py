import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from intelligence.circuit_breaker import ProviderCircuitBreaker, CircuitOpenError


@pytest.mark.asyncio
async def test_circuit_starts_closed():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_circuit_stays_closed_on_success():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)

    async def success():
        return "ok"

    result = await cb.call(success)
    assert result == "ok"
    assert cb.state == "closed"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)

    async def fail():
        raise ValueError("boom")

    for _ in range(3):
        with pytest.raises(ValueError):
            await cb.call(fail)

    assert cb.state == "open"
    assert cb.failures == 3


@pytest.mark.asyncio
async def test_circuit_open_raises_circuit_open_error():
    cb = ProviderCircuitBreaker(failure_threshold=1, reset_timeout=60)

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"

    with pytest.raises(CircuitOpenError):
        await cb.call(fail)


@pytest.mark.asyncio
async def test_circuit_resets_on_success_after_failure():
    cb = ProviderCircuitBreaker(failure_threshold=3, reset_timeout=60)

    async def fail():
        raise ValueError("boom")

    async def success():
        return "ok"

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(fail)

    assert cb.state == "closed"
    assert cb.failures == 2

    result = await cb.call(success)
    assert result == "ok"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_half_open_after_reset_timeout():
    cb = ProviderCircuitBreaker(failure_threshold=1, reset_timeout=1)

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"

    cb.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=2)

    async def success():
        return "recovered"

    result = await cb.call(success)
    assert result == "recovered"
    assert cb.state == "closed"
    assert cb.failures == 0


@pytest.mark.asyncio
async def test_circuit_half_open_failure_reopens():
    cb = ProviderCircuitBreaker(failure_threshold=1, reset_timeout=1)

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"

    cb.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=2)

    with pytest.raises(ValueError):
        await cb.call(fail)

    assert cb.state == "open"
