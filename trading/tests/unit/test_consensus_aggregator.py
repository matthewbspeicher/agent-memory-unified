import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from integrations.bittensor.consensus_aggregator import MinerConsensusAggregator

@pytest.mark.asyncio
async def test_consensus_aggregator_emits_consensus():
    signal_bus = SignalBus()
    aggregator = MinerConsensusAggregator(signal_bus, window_minutes=5)
    await aggregator.start()

    published_signals = []
    
    async def mock_publish(signal: AgentSignal):
        if signal.signal_type == "bittensor_consensus":
            published_signals.append(signal)

    signal_bus.publish = AsyncMock(side_effect=mock_publish)

    # Emit some miner positions
    now = datetime.now(timezone.utc)
    base_payload = {
        "symbol": "BTCUSD",
        "leverage": 1.0,
        "price": 65000.0,
        "open_ms": int(now.timestamp() * 1000)
    }

    # 3 bullish miners
    for i in range(3):
        payload = base_payload.copy()
        payload["miner_hotkey"] = f"hotkey{i}"
        payload["direction"] = "long"
        
        sig = AgentSignal(
            source_agent="taoshi_bridge",
            signal_type="bittensor_miner_position",
            payload=payload,
            expires_at=now + timedelta(minutes=30)
        )
        await aggregator._handle_miner_position(sig)

    # Wait for processing
    await asyncio.sleep(0.1)

    assert len(published_signals) > 0
    latest = published_signals[-1]
    assert latest.payload["symbol"] == "BTCUSD"
    assert latest.payload["direction"] == "bullish"
    assert latest.payload["confidence"] == 1.0
    assert latest.payload["miner_count"] == 3

    await aggregator.stop()

@pytest.mark.asyncio
async def test_stale_positions_are_ignored():
    signal_bus = SignalBus()
    aggregator = MinerConsensusAggregator(signal_bus, window_minutes=5)
    await aggregator.start()

    published_signals = []
    
    async def mock_publish(signal: AgentSignal):
        if signal.signal_type == "bittensor_consensus":
            published_signals.append(signal)

    signal_bus.publish = AsyncMock(side_effect=mock_publish)

    # Emit a stale miner position
    now = datetime.now(timezone.utc)
    payload = {
        "symbol": "ETHUSD",
        "miner_hotkey": "hotkey1",
        "direction": "long",
        "leverage": 1.0,
        "price": 3500.0,
        "open_ms": int((now - timedelta(minutes=10)).timestamp() * 1000) # 10 mins old
    }

    sig = AgentSignal(
        source_agent="taoshi_bridge",
        signal_type="bittensor_miner_position",
        payload=payload,
        expires_at=now + timedelta(minutes=30)
    )
    
    await aggregator._handle_miner_position(sig)
    await asyncio.sleep(0.1)

    # Should not emit consensus for purely stale data
    assert len(published_signals) == 0

    await aggregator.stop()
