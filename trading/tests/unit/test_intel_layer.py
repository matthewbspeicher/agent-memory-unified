"""Tests for IntelligenceLayer orchestrator."""
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from intelligence.config import IntelligenceConfig
from intelligence.models import IntelReport
from intelligence.layer import IntelligenceLayer


def _make_report(source: str, score: float, confidence: float, veto: bool = False, veto_reason: str | None = None) -> IntelReport:
    return IntelReport(
        source=source,
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=score,
        confidence=confidence,
        veto=veto,
        veto_reason=veto_reason,
        details={},
    )


def _make_consensus_signal(symbol: str = "BTCUSD", direction: str = "bullish", confidence: float = 0.8) -> AgentSignal:
    return AgentSignal(
        source_agent="miner_consensus_aggregator",
        signal_type="bittensor_consensus",
        payload={
            "symbol": symbol,
            "timeframe": "5m",
            "direction": direction,
            "confidence": confidence,
            "expected_return": 0.003,
            "window_id": "20260407-1200",
            "miner_count": 5,
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )


@pytest.mark.asyncio
async def test_layer_enriches_consensus_signal():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    layer._on_chain = MagicMock()
    layer._on_chain.analyze = AsyncMock(return_value=_make_report("on_chain", 0.5, 0.8))
    layer._sentiment = MagicMock()
    layer._sentiment.analyze = AsyncMock(return_value=_make_report("sentiment", 0.3, 0.6))
    layer._anomaly = MagicMock()
    layer._anomaly.analyze = AsyncMock(return_value=_make_report("anomaly", 0.1, 0.5))

    published = []
    original_publish = signal_bus.publish

    async def capture_publish(signal: AgentSignal):
        published.append(signal)
        await original_publish(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    consensus = _make_consensus_signal()
    await layer._handle_consensus(consensus)

    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    payload = enriched[0].payload
    assert payload["symbol"] == "BTCUSD"
    assert "enriched_confidence" in payload
    assert payload["enriched_confidence"] >= consensus.payload["confidence"]
    assert payload["vetoed"] is False

    await layer.stop()


@pytest.mark.asyncio
async def test_layer_veto_blocks_signal():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    layer._on_chain = MagicMock()
    layer._on_chain.analyze = AsyncMock(return_value=_make_report("on_chain", -0.8, 0.9, veto=True, veto_reason="massive inflow"))
    layer._sentiment = MagicMock()
    layer._sentiment.analyze = AsyncMock(return_value=_make_report("sentiment", 0.2, 0.5))
    layer._anomaly = MagicMock()
    layer._anomaly.analyze = AsyncMock(return_value=_make_report("anomaly", 0.0, 0.3))

    published = []

    async def capture_publish(signal: AgentSignal):
        published.append(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    await layer._handle_consensus(_make_consensus_signal())

    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    assert enriched[0].payload["vetoed"] is True
    assert enriched[0].payload["enriched_confidence"] == 0.0

    await layer.stop()


@pytest.mark.asyncio
async def test_layer_handles_all_providers_failing():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    layer._on_chain = MagicMock()
    layer._on_chain.analyze = AsyncMock(side_effect=Exception("fail"))
    layer._sentiment = MagicMock()
    layer._sentiment.analyze = AsyncMock(side_effect=Exception("fail"))
    layer._anomaly = MagicMock()
    layer._anomaly.analyze = AsyncMock(side_effect=Exception("fail"))

    published = []

    async def capture_publish(signal: AgentSignal):
        published.append(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    await layer._handle_consensus(_make_consensus_signal(confidence=0.75))

    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    assert enriched[0].payload["enriched_confidence"] == 0.75
    assert enriched[0].payload["vetoed"] is False

    await layer.stop()


@pytest.mark.asyncio
async def test_layer_get_status():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=True)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    status = layer.get_status()
    assert status["enabled"] is True
    assert "providers" in status
    assert "on_chain" in status["providers"]
    assert "sentiment" in status["providers"]
    assert "anomaly" in status["providers"]


@pytest.mark.asyncio
async def test_layer_disabled_passthrough():
    signal_bus = SignalBus()
    config = IntelligenceConfig(enabled=False)
    layer = IntelligenceLayer(signal_bus=signal_bus, config=config)

    published = []

    async def capture_publish(signal: AgentSignal):
        published.append(signal)

    signal_bus.publish = capture_publish

    await layer.start()
    await layer._handle_consensus(_make_consensus_signal(confidence=0.65))

    enriched = [s for s in published if s.signal_type == "intel_enriched_consensus"]
    assert len(enriched) == 1
    assert enriched[0].payload["enriched_confidence"] == 0.65
    assert enriched[0].payload["vetoed"] is False

    await layer.stop()
