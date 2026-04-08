# tests/unit/competition/test_tracker.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from competition.tracker import SignalTracker, TrackedSignal


class MockAgentSignal:
    """Mock AgentSignal for testing."""

    def __init__(
        self,
        source_agent: str,
        signal_type: str,
        payload: dict,
        confidence: float = None,
        timestamp: datetime = None,
    ):
        self.source_agent = source_agent
        self.signal_type = signal_type
        self.payload = payload
        self.confidence = confidence
        self.timestamp = timestamp or datetime.now(timezone.utc)


class TestSignalTracker:
    @pytest.mark.asyncio
    async def test_track_signal_from_agent(self):
        tracker = SignalTracker()
        signal = MockAgentSignal(
            source_agent="rsi_scanner",
            signal_type="opportunity",
            payload={"symbol": "BTCUSD", "direction": "long", "confidence": 0.85},
            timestamp=datetime.now(timezone.utc),
        )
        await tracker.on_signal(signal)
        assert len(tracker.pending_signals) == 1
        tracked = tracker.pending_signals[0]
        assert tracked.source_agent == "rsi_scanner"
        assert tracked.asset == "BTC"
        assert tracked.direction == "long"
        assert tracked.confidence == 0.85

    @pytest.mark.asyncio
    async def test_drain_returns_and_clears(self):
        tracker = SignalTracker()
        signal = MockAgentSignal(
            source_agent="rsi_scanner",
            signal_type="opportunity",
            payload={"symbol": "BTCUSD", "direction": "long", "confidence": 0.7},
            timestamp=datetime.now(timezone.utc),
        )
        await tracker.on_signal(signal)
        drained = tracker.drain()
        assert len(drained) == 1
        assert len(tracker.pending_signals) == 0

    @pytest.mark.asyncio
    async def test_ignores_non_opportunity_signals(self):
        tracker = SignalTracker()
        signal = MockAgentSignal(
            source_agent="meta_agent",
            signal_type="meta_update",
            payload={},
            timestamp=datetime.now(timezone.utc),
        )
        await tracker.on_signal(signal)
        assert len(tracker.pending_signals) == 0

    def test_normalize_symbol_strips_usd(self):
        tracker = SignalTracker()
        assert tracker._normalize_asset("BTCUSD") == "BTC"
        assert tracker._normalize_asset("ETHUSD") == "ETH"
        assert tracker._normalize_asset("BTC/USDT") == "BTC"
        assert tracker._normalize_asset("BTC") == "BTC"
