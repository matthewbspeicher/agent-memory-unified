"""Tests for the normalized `intel_sentiment` SignalBus topic (ADR-0011).

Covers:
1. `IntelSentimentPayload` validates correctly (score/confidence bounds, defaults).
2. `IntelligenceLayer._publish_sentiment` emits a typed signal that
   round-trips through the registry.
3. `Agent.consume_sentiment(symbol)` returns the freshest payload, filters
   by symbol, and respects `max_age_seconds`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agents.base import Agent
from agents.models import (
    ActionLevel,
    AgentConfig,
    AgentSignal,
    Opportunity,
)
from data.signal_bus import SignalBus
from data.signal_types import IntelSentimentPayload, registry
from intelligence.layer import IntelligenceLayer
from intelligence.models import IntelReport


# ---------------------------------------------------------------------------
# 1. Payload validation
# ---------------------------------------------------------------------------


class TestIntelSentimentPayload:
    def test_valid_minimal(self):
        payload = {"symbol": "BTCUSD", "score": 0.3, "confidence": 0.7}
        model = IntelSentimentPayload.model_validate(payload)
        assert model.symbol == "BTCUSD"
        assert model.score == 0.3
        assert model.confidence == 0.7
        assert model.sources == {}

    def test_valid_full(self):
        payload = {
            "symbol": "ETHUSD",
            "score": -0.4,
            "confidence": 0.85,
            "sources": {
                "fear_greed_value": 20,
                "lunarcrush_galaxy_score": 65.0,
                "lunarcrush_alt_rank": 12.0,
                "av_sentiment_score": -0.3,
            },
        }
        model = IntelSentimentPayload.model_validate(payload)
        assert model.score == -0.4
        assert model.sources["fear_greed_value"] == 20

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            IntelSentimentPayload.model_validate(
                {"symbol": "BTCUSD", "score": 1.5, "confidence": 0.5}
            )
        with pytest.raises(ValidationError):
            IntelSentimentPayload.model_validate(
                {"symbol": "BTCUSD", "score": -1.5, "confidence": 0.5}
            )

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            IntelSentimentPayload.model_validate(
                {"symbol": "BTCUSD", "score": 0.0, "confidence": 1.5}
            )

    def test_registered(self):
        assert "intel_sentiment" in registry
        assert registry.get("intel_sentiment") is IntelSentimentPayload


# ---------------------------------------------------------------------------
# 2. IntelligenceLayer publishes the topic
# ---------------------------------------------------------------------------


@dataclass
class _FakeConfig:
    """Minimal stub matching the IntelligenceConfig surface used by the layer."""

    enabled: bool = True
    coinglass_api_key: str | None = None
    lunarcrush_api_key: str | None = None
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_seconds: int = 60
    timeout_ms: int = 5000
    max_adjustment_pct: float = 0.5
    weights: dict = None
    risk_var_threshold_pct: float = 0.05
    risk_horizon_days: int = 1

    def __post_init__(self):
        if self.weights is None:
            self.weights = {
                "on_chain": 0.2,
                "sentiment": 0.15,
                "anomaly": 0.1,
                "order_flow": 0.1,
                "regime": 0.15,
                "risk_audit": 0.1,
                "derivatives": 0.1,
                "knowledge_graph": 0.1,
            }


class TestPublishSentiment:
    @pytest.mark.asyncio
    async def test_publish_emits_typed_signal(self):
        bus = SignalBus()
        layer = IntelligenceLayer(signal_bus=bus, config=_FakeConfig())

        report = IntelReport(
            source="sentiment",
            symbol="BTCUSD",
            timestamp=datetime.now(timezone.utc),
            score=0.25,
            confidence=0.7,
            veto=False,
            details={"fear_greed_value": 35, "lunarcrush_galaxy_score": 72.0},
        )

        await layer._publish_sentiment(report)

        signals = bus.query(signal_type="intel_sentiment")
        assert len(signals) == 1
        s = signals[0]
        assert s.source_agent == "intelligence_layer"
        assert s.payload["symbol"] == "BTCUSD"
        assert s.payload["score"] == 0.25
        assert s.payload["confidence"] == 0.7
        assert s.payload["sources"]["fear_greed_value"] == 35

    @pytest.mark.asyncio
    async def test_publish_swallows_validation_errors(self):
        """Best-effort: a malformed report must not break enrichment."""
        bus = SignalBus()
        layer = IntelligenceLayer(signal_bus=bus, config=_FakeConfig())

        # score out of range — would fail validation
        bad = IntelReport(
            source="sentiment",
            symbol="BTCUSD",
            timestamp=datetime.now(timezone.utc),
            score=9.9,  # invalid
            confidence=0.5,
            veto=False,
            details={},
        )
        # Should not raise.
        await layer._publish_sentiment(bad)

        assert bus.query(signal_type="intel_sentiment") == []


# ---------------------------------------------------------------------------
# 3. Agent.consume_sentiment helper
# ---------------------------------------------------------------------------


class _DummyAgent(Agent):
    @property
    def description(self) -> str:
        return "test-only stub"

    async def scan(self, data):
        return []


def _make_agent(name: str = "test") -> _DummyAgent:
    return _DummyAgent(
        AgentConfig(
            name=name,
            strategy="dummy",
            schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
        )
    )


def _publish_sentiment_sync(bus: SignalBus, symbol: str, score: float, age_s: int = 0):
    """Helper: publish via the bus directly with a backdated timestamp."""
    sig = AgentSignal(
        source_agent="intelligence_layer",
        signal_type="intel_sentiment",
        payload={
            "symbol": symbol,
            "score": score,
            "confidence": 0.6,
            "sources": {},
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    if age_s:
        sig.timestamp = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    asyncio.get_event_loop().run_until_complete(bus.publish(sig))


class TestConsumeSentiment:
    @pytest.mark.asyncio
    async def test_returns_none_without_bus(self):
        agent = _make_agent()
        assert agent.consume_sentiment("BTCUSD") is None

    @pytest.mark.asyncio
    async def test_returns_payload_when_fresh(self):
        bus = SignalBus()
        agent = _make_agent()
        agent.signal_bus = bus

        await bus.publish(
            AgentSignal(
                source_agent="intelligence_layer",
                signal_type="intel_sentiment",
                payload={
                    "symbol": "BTCUSD",
                    "score": 0.4,
                    "confidence": 0.8,
                    "sources": {"fear_greed_value": 25},
                },
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        out = agent.consume_sentiment("BTCUSD")
        assert out is not None
        assert out["score"] == 0.4
        assert out["sources"]["fear_greed_value"] == 25

    @pytest.mark.asyncio
    async def test_filters_by_symbol(self):
        bus = SignalBus()
        agent = _make_agent()
        agent.signal_bus = bus

        await bus.publish(
            AgentSignal(
                source_agent="intelligence_layer",
                signal_type="intel_sentiment",
                payload={
                    "symbol": "ETHUSD",
                    "score": -0.2,
                    "confidence": 0.5,
                    "sources": {},
                },
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )

        assert agent.consume_sentiment("BTCUSD") is None
        eth = agent.consume_sentiment("ETHUSD")
        assert eth is not None
        assert eth["score"] == -0.2

    @pytest.mark.asyncio
    async def test_respects_max_age(self):
        bus = SignalBus()
        agent = _make_agent()
        agent.signal_bus = bus

        # Publish, then backdate the timestamp.
        sig = AgentSignal(
            source_agent="intelligence_layer",
            signal_type="intel_sentiment",
            payload={
                "symbol": "BTCUSD",
                "score": 0.1,
                "confidence": 0.5,
                "sources": {},
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        await bus.publish(sig)
        # Mutate stored signal timestamp to be old.
        stored = bus.query(signal_type="intel_sentiment")[0]
        stored.timestamp = datetime.now(timezone.utc) - timedelta(seconds=600)

        # Default max_age (300s) — should reject.
        assert agent.consume_sentiment("BTCUSD") is None
        # Generous max_age — should accept.
        assert agent.consume_sentiment("BTCUSD", max_age_seconds=900) is not None

    @pytest.mark.asyncio
    async def test_returns_newest_when_multiple(self):
        bus = SignalBus()
        agent = _make_agent()
        agent.signal_bus = bus

        for score in (0.1, 0.2, 0.3):
            await bus.publish(
                AgentSignal(
                    source_agent="intelligence_layer",
                    signal_type="intel_sentiment",
                    payload={
                        "symbol": "BTCUSD",
                        "score": score,
                        "confidence": 0.5,
                        "sources": {},
                    },
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                )
            )

        out = agent.consume_sentiment("BTCUSD")
        assert out is not None
        # Newest signal has score=0.3
        assert out["score"] == 0.3
