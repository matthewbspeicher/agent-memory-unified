import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from agents.models import AgentSignal
from data.signal_bus import SignalBus

@pytest.mark.asyncio
async def test_signal_bus_publish_and_query():
    bus = SignalBus()
    now = datetime.now(timezone.utc)
    sig = AgentSignal(
        source_agent="sentiment_scout",
        signal_type="sentiment",
        payload={"score": 0.8},
        expires_at=now + timedelta(minutes=5)
    )
    await bus.publish(sig)
    
    active = bus.query(signal_type="sentiment")
    assert len(active) == 1
    assert active[0].payload["score"] == 0.8

@pytest.mark.asyncio
async def test_signal_bus_ignores_expired():
    bus = SignalBus()
    now = datetime.now(timezone.utc)
    sig = AgentSignal(
        source_agent="sentiment_scout",
        signal_type="sentiment",
        payload={"score": 0.8},
        expires_at=now - timedelta(minutes=1) # Already expired
    )
    await bus.publish(sig)
    
    active = bus.query(signal_type="sentiment")
    assert len(active) == 0


@pytest.mark.asyncio
async def test_signal_bus_prunes_on_publish():
    bus = SignalBus()
    now = datetime.now(timezone.utc)
    expired = AgentSignal(
        source_agent="old",
        signal_type="stale",
        payload={},
        expires_at=now - timedelta(minutes=1),
    )
    bus._signals.append(expired)
    assert len(bus._signals) == 1

    fresh = AgentSignal(
        source_agent="new",
        signal_type="fresh",
        payload={},
        expires_at=now + timedelta(minutes=5),
    )
    await bus.publish(fresh)
    assert len(bus._signals) == 1
    assert bus._signals[0].signal_type == "fresh"


@pytest.mark.asyncio
async def test_signal_bus_caps_at_max():
    bus = SignalBus()
    now = datetime.now(timezone.utc)
    for i in range(1005):
        sig = AgentSignal(
            source_agent=f"agent_{i}",
            signal_type="test",
            payload={},
            expires_at=now + timedelta(minutes=5),
        )
        await bus.publish(sig)
    assert len(bus._signals) <= 1000
