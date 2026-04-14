"""Unit tests for typed signal contracts and SignalBus validation.

Tests verify:
1. All 10 signal payload models validate correctly with valid data
2. Each model rejects invalid/missing fields (extra fields, wrong types, out-of-range values)
3. SignalTypeRegistry.validate() returns coerced defaults for known types
4. SignalTypeRegistry.validate() passes through unknown types with no crash
5. SignalTypeRegistry.validate() raises ValueError for invalid payloads on known types
6. AgentSignal.validate_payload() works with and without explicit registry
7. SignalBus.publish() validates and coerces payloads before delivery to subscribers
"""

import pytest
from datetime import datetime, timezone, timedelta
from pydantic import ValidationError

from data.signal_types import (
    registry,
    SignalTypeRegistry,
    SignalPayload,
    BittensorMinerPositionPayload,
    BittensorConsensusPayload,
    IntelEnrichedConsensusPayload,
    RegimeUpdatePayload,
    NewsEventPayload,
    VolumeAnomalyPayload,
    PriceDislocationPayload,
    SentimentSpikePayload,
    SpreadConvergencePayload,
    CloseSignalPayload,
)
from agents.models import AgentSignal
from data.signal_bus import SignalBus


@pytest.fixture
def custom_registry():
    """Create a fresh registry for isolated tests."""
    return SignalTypeRegistry()


@pytest.fixture
def expires_soon():
    """Expiration time 1 hour in the future."""
    return datetime.now(timezone.utc) + timedelta(hours=1)


class TestBittensorMinerPositionPayload:
    """Test BittensorMinerPositionPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with only required fields."""
        payload = {
            "miner_hotkey": "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe",
            "symbol": "BTC/USD",
            "direction": "long",
        }
        model = BittensorMinerPositionPayload.model_validate(payload)
        assert model.miner_hotkey == "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe"
        assert model.symbol == "BTC/USD"
        assert model.direction == "long"
        assert model.leverage == 0.0
        assert model.price == 0.0

    def test_valid_full(self):
        """Valid payload with all fields."""
        payload = {
            "miner_hotkey": "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe",
            "symbol": "ETH/USD",
            "direction": "short",
            "leverage": 2.5,
            "price": 1850.50,
            "position_uuid": "uuid-123",
            "order_type": "LIMIT",
            "open_ms": 1704067200000,
            "signal_reason": "breakout",
            "order_count": 3,
        }
        model = BittensorMinerPositionPayload.model_validate(payload)
        assert model.leverage == 2.5
        assert model.price == 1850.50

    def test_invalid_direction(self):
        """Reject invalid direction literal."""
        payload = {
            "miner_hotkey": "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe",
            "symbol": "BTC/USD",
            "direction": "sideways",
        }
        with pytest.raises(ValidationError):
            BittensorMinerPositionPayload.model_validate(payload)

    def test_missing_required_field(self):
        """Reject payload missing required field."""
        payload = {
            "miner_hotkey": "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe",
            "direction": "long",
        }
        with pytest.raises(ValidationError):
            BittensorMinerPositionPayload.model_validate(payload)

    def test_extra_fields_rejected(self):
        """Reject payload with extra unknown fields."""
        payload = {
            "miner_hotkey": "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe",
            "symbol": "BTC/USD",
            "direction": "long",
            "unknown_field": "should_fail",
        }
        with pytest.raises(ValidationError):
            BittensorMinerPositionPayload.model_validate(payload)

    def test_wrong_type_leverage(self):
        """Reject non-numeric leverage."""
        payload = {
            "miner_hotkey": "5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe",
            "symbol": "BTC/USD",
            "direction": "long",
            "leverage": "not_a_number",
        }
        with pytest.raises(ValidationError):
            BittensorMinerPositionPayload.model_validate(payload)


class TestBittensorConsensusPayload:
    """Test BittensorConsensusPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.75,
            "miner_count": 5,
        }
        model = BittensorConsensusPayload.model_validate(payload)
        assert model.symbol == "BTC/USD"
        assert model.confidence == 0.75
        assert model.miner_count == 5

    def test_confidence_bounds(self):
        """Confidence must be in [0.0, 1.0]."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.0,
            "miner_count": 1,
        }
        model = BittensorConsensusPayload.model_validate(payload)
        assert model.confidence == 0.0

        payload["confidence"] = 1.0
        model = BittensorConsensusPayload.model_validate(payload)
        assert model.confidence == 1.0

        payload["confidence"] = 1.1
        with pytest.raises(ValidationError):
            BittensorConsensusPayload.model_validate(payload)

    def test_miner_count_minimum(self):
        """miner_count must be >= 1."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.5,
            "miner_count": 0,
        }
        with pytest.raises(ValidationError):
            BittensorConsensusPayload.model_validate(payload)

    def test_invalid_direction(self):
        """Reject invalid direction."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "bullish",
            "confidence": 0.5,
            "miner_count": 1,
        }
        with pytest.raises(ValidationError):
            BittensorConsensusPayload.model_validate(payload)

    def test_coerce_defaults(self):
        """Verify defaults are coerced correctly."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.5,
            "miner_count": 1,
        }
        model = BittensorConsensusPayload.model_validate(payload)
        assert model.expected_return == 0.0
        assert model.window_id == ""


class TestIntelEnrichedConsensusPayload:
    """Test IntelEnrichedConsensusPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.75,
            "miner_count": 5,
            "enriched_confidence": 0.80,
        }
        model = IntelEnrichedConsensusPayload.model_validate(payload)
        assert model.enriched_confidence == 0.80
        assert model.vetoed is False
        assert model.intel == {}

    def test_enriched_confidence_bounds(self):
        """enriched_confidence must be in [0.0, 1.0]."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.75,
            "miner_count": 5,
            "enriched_confidence": 1.5,
        }
        with pytest.raises(ValidationError):
            IntelEnrichedConsensusPayload.model_validate(payload)

    def test_vetoed_flag(self):
        """Test vetoed boolean flag."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.75,
            "miner_count": 5,
            "enriched_confidence": 0.80,
            "vetoed": True,
            "intel": {"veto_reason": "regime_mismatch"},
        }
        model = IntelEnrichedConsensusPayload.model_validate(payload)
        assert model.vetoed is True
        assert model.intel["veto_reason"] == "regime_mismatch"

    def test_inherits_from_consensus(self):
        """Verify inheritance from BittensorConsensusPayload."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.75,
            "miner_count": 5,
            "enriched_confidence": 0.80,
            "expected_return": 0.05,
            "window_id": "window-123",
        }
        model = IntelEnrichedConsensusPayload.model_validate(payload)
        assert model.expected_return == 0.05
        assert model.window_id == "window-123"


class TestRegimeUpdatePayload:
    """Test RegimeUpdatePayload validation."""

    def test_valid_minimal(self):
        """Valid payload with defaults."""
        payload = {}
        model = RegimeUpdatePayload.model_validate(payload)
        assert model.market_phase == "unknown"
        assert model.volatility == "normal"
        assert model.trend == "neutral"
        assert model.regime == "unknown"

    def test_valid_full(self):
        """Valid payload with all fields."""
        payload = {
            "market_phase": "expansion",
            "volatility": "high",
            "trend": "uptrend",
            "regime": "bull_market",
        }
        model = RegimeUpdatePayload.model_validate(payload)
        assert model.market_phase == "expansion"

    def test_extra_fields_rejected(self):
        """Reject extra fields."""
        payload = {
            "market_phase": "expansion",
            "extra_field": "should_fail",
        }
        with pytest.raises(ValidationError):
            RegimeUpdatePayload.model_validate(payload)


class TestNewsEventPayload:
    """Test NewsEventPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "ticker": "AAPL",
            "headline": "Apple announces new product",
            "sentiment": 0.5,
            "confidence": 0.8,
            "direction": "long",
        }
        model = NewsEventPayload.model_validate(payload)
        assert model.ticker == "AAPL"
        assert model.source == ""

    def test_sentiment_bounds(self):
        """Sentiment must be in [-1.0, 1.0]."""
        payload = {
            "ticker": "AAPL",
            "headline": "News",
            "sentiment": -1.0,
            "confidence": 0.8,
            "direction": "long",
        }
        model = NewsEventPayload.model_validate(payload)
        assert model.sentiment == -1.0

        payload["sentiment"] = 1.5
        with pytest.raises(ValidationError):
            NewsEventPayload.model_validate(payload)

    def test_confidence_bounds(self):
        """Confidence must be in [0.0, 1.0]."""
        payload = {
            "ticker": "AAPL",
            "headline": "News",
            "sentiment": 0.5,
            "confidence": 1.5,
            "direction": "long",
        }
        with pytest.raises(ValidationError):
            NewsEventPayload.model_validate(payload)

    def test_invalid_direction(self):
        """Reject invalid direction."""
        payload = {
            "ticker": "AAPL",
            "headline": "News",
            "sentiment": 0.5,
            "confidence": 0.8,
            "direction": "sideways",
        }
        with pytest.raises(ValidationError):
            NewsEventPayload.model_validate(payload)


class TestVolumeAnomalyPayload:
    """Test VolumeAnomalyPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "ticker": "BTC",
            "magnitude": 2.5,
            "volume": 1000000,
            "avg_volume": 500000,
            "direction": "bullish",
        }
        model = VolumeAnomalyPayload.model_validate(payload)
        assert model.magnitude == 2.5

    def test_magnitude_positive(self):
        """Magnitude must be > 0."""
        payload = {
            "ticker": "BTC",
            "magnitude": 0,
            "volume": 1000000,
            "avg_volume": 500000,
            "direction": "bullish",
        }
        with pytest.raises(ValidationError):
            VolumeAnomalyPayload.model_validate(payload)

    def test_volume_non_negative(self):
        """Volume must be >= 0."""
        payload = {
            "ticker": "BTC",
            "magnitude": 2.5,
            "volume": -1,
            "avg_volume": 500000,
            "direction": "bullish",
        }
        with pytest.raises(ValidationError):
            VolumeAnomalyPayload.model_validate(payload)

    def test_avg_volume_non_negative(self):
        """avg_volume must be >= 0."""
        payload = {
            "ticker": "BTC",
            "magnitude": 2.5,
            "volume": 1000000,
            "avg_volume": -1,
            "direction": "bullish",
        }
        with pytest.raises(ValidationError):
            VolumeAnomalyPayload.model_validate(payload)

    def test_invalid_direction(self):
        """Reject invalid direction."""
        payload = {
            "ticker": "BTC",
            "magnitude": 2.5,
            "volume": 1000000,
            "avg_volume": 500000,
            "direction": "sideways",
        }
        with pytest.raises(ValidationError):
            VolumeAnomalyPayload.model_validate(payload)


class TestPriceDislocationPayload:
    """Test PriceDislocationPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "ticker": "BTC",
            "move_pct": 5.5,
            "prev_price": 40000,
            "current_price": 42200,
            "direction": "bullish",
        }
        model = PriceDislocationPayload.model_validate(payload)
        assert model.move_pct == 5.5

    def test_price_non_negative(self):
        """Prices must be >= 0."""
        payload = {
            "ticker": "BTC",
            "move_pct": 5.5,
            "prev_price": -1,
            "current_price": 42200,
            "direction": "bullish",
        }
        with pytest.raises(ValidationError):
            PriceDislocationPayload.model_validate(payload)

    def test_invalid_direction(self):
        """Reject invalid direction."""
        payload = {
            "ticker": "BTC",
            "move_pct": 5.5,
            "prev_price": 40000,
            "current_price": 42200,
            "direction": "sideways",
        }
        with pytest.raises(ValidationError):
            PriceDislocationPayload.model_validate(payload)


class TestSentimentSpikePayload:
    """Test SentimentSpikePayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "ticker": "BTC",
            "bullish_count": 100,
            "bearish_count": 20,
            "imbalance": 0.6,
            "direction": "bullish",
        }
        model = SentimentSpikePayload.model_validate(payload)
        assert model.bullish_count == 100

    def test_counts_non_negative(self):
        """Counts must be >= 0."""
        payload = {
            "ticker": "BTC",
            "bullish_count": -1,
            "bearish_count": 20,
            "imbalance": 0.6,
            "direction": "bullish",
        }
        with pytest.raises(ValidationError):
            SentimentSpikePayload.model_validate(payload)

    def test_imbalance_bounds(self):
        """Imbalance must be in [-1.0, 1.0]."""
        payload = {
            "ticker": "BTC",
            "bullish_count": 100,
            "bearish_count": 20,
            "imbalance": 1.5,
            "direction": "bullish",
        }
        with pytest.raises(ValidationError):
            SentimentSpikePayload.model_validate(payload)

    def test_invalid_direction(self):
        """Reject invalid direction."""
        payload = {
            "ticker": "BTC",
            "bullish_count": 100,
            "bearish_count": 20,
            "imbalance": 0.6,
            "direction": "neutral_but_bullish",
        }
        with pytest.raises(ValidationError):
            SentimentSpikePayload.model_validate(payload)


class TestSpreadConvergencePayload:
    """Test SpreadConvergencePayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required fields."""
        payload = {
            "pair": "BTC/USD",
            "spread_bps": 5.5,
            "threshold_bps": 10.0,
        }
        model = SpreadConvergencePayload.model_validate(payload)
        assert model.pair == "BTC/USD"
        assert model.direction == "narrowing"

    def test_valid_full(self):
        """Valid payload with all fields."""
        payload = {
            "pair": "BTC/USD",
            "spread_bps": 5.5,
            "threshold_bps": 10.0,
            "direction": "widening",
        }
        model = SpreadConvergencePayload.model_validate(payload)
        assert model.direction == "widening"

    def test_invalid_direction(self):
        """Reject invalid direction."""
        payload = {
            "pair": "BTC/USD",
            "spread_bps": 5.5,
            "threshold_bps": 10.0,
            "direction": "converging",
        }
        with pytest.raises(ValidationError):
            SpreadConvergencePayload.model_validate(payload)


class TestCloseSignalPayload:
    """Test CloseSignalPayload validation."""

    def test_valid_minimal(self):
        """Valid payload with required field."""
        payload = {"symbol": "BTC/USD"}
        model = CloseSignalPayload.model_validate(payload)
        assert model.symbol == "BTC/USD"
        assert model.reason == ""
        assert model.urgency == "medium"

    def test_valid_full(self):
        """Valid payload with all fields."""
        payload = {
            "symbol": "BTC/USD",
            "reason": "stop_loss_hit",
            "urgency": "high",
        }
        model = CloseSignalPayload.model_validate(payload)
        assert model.reason == "stop_loss_hit"

    def test_invalid_urgency(self):
        """Reject invalid urgency."""
        payload = {
            "symbol": "BTC/USD",
            "urgency": "critical",
        }
        with pytest.raises(ValidationError):
            CloseSignalPayload.model_validate(payload)


class TestSignalTypeRegistry:
    """Test SignalTypeRegistry validation and registration."""

    def test_registry_has_all_types(self):
        """Global registry has all 10 signal types registered."""
        expected_types = [
            "bittensor_miner_position",
            "bittensor_consensus",
            "intel_enriched_consensus",
            "regime_update",
            "news_event",
            "volume_anomaly",
            "price_dislocation",
            "sentiment_spike",
            "spread_convergence",
            "close",
        ]
        known = registry.known_types()
        assert len(known) == 10
        for signal_type in expected_types:
            assert signal_type in known

    def test_validate_known_type_valid_payload(self):
        """validate() returns coerced dict for valid payload."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.75,
            "miner_count": 5,
        }
        result = registry.validate("bittensor_consensus", payload)
        assert isinstance(result, dict)
        assert result["symbol"] == "BTC/USD"
        assert result["expected_return"] == 0.0

    def test_validate_known_type_invalid_payload(self):
        """validate() raises ValueError for invalid payload on known type."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "invalid_direction",
            "confidence": 0.75,
            "miner_count": 5,
        }
        with pytest.raises(ValueError) as exc_info:
            registry.validate("bittensor_consensus", payload)
        assert "Payload validation failed" in str(exc_info.value)

    def test_validate_unknown_type_passes_through(self):
        """validate() passes through unknown types with warning."""
        payload = {"custom_field": "custom_value"}
        result = registry.validate("unknown_signal_type", payload)
        assert result == payload

    def test_validate_unknown_type_no_crash(self):
        """validate() doesn't crash on unknown types."""
        payload = {"any": "data"}
        result = registry.validate("future_signal_type", payload)
        assert result == payload

    def test_register_new_type(self, custom_registry):
        """Can register new signal types."""

        class CustomPayload(SignalPayload):
            custom_field: str

        custom_registry.register("custom_type", CustomPayload)
        assert "custom_type" in custom_registry
        assert custom_registry.get("custom_type") is CustomPayload

    def test_register_overwrites_with_warning(self, custom_registry):
        """Registering same type twice logs warning."""

        class PayloadV1(SignalPayload):
            field: str

        class PayloadV2(SignalPayload):
            field: str

        custom_registry.register("my_type", PayloadV1)
        custom_registry.register("my_type", PayloadV2)
        assert custom_registry.get("my_type") is PayloadV2

    def test_get_returns_none_for_unknown(self, custom_registry):
        """get() returns None for unknown types."""
        assert custom_registry.get("nonexistent") is None

    def test_contains_operator(self, custom_registry):
        """__contains__ works for type checking."""

        class MyPayload(SignalPayload):
            field: str

        custom_registry.register("my_type", MyPayload)
        assert "my_type" in custom_registry
        assert "nonexistent" not in custom_registry


class TestAgentSignalValidatePayload:
    """Test AgentSignal.validate_payload() method."""

    def test_validate_with_explicit_registry(self, expires_soon):
        """validate_payload() works with explicit registry."""
        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )
        validated = signal.validate_payload(registry)
        assert validated["symbol"] == "BTC/USD"
        assert validated["expected_return"] == 0.0

    def test_validate_without_registry_uses_default(self, expires_soon):
        """validate_payload() uses default registry when not provided."""
        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )
        validated = signal.validate_payload()
        assert validated["symbol"] == "BTC/USD"

    def test_validate_raises_on_invalid_payload(self, expires_soon):
        """validate_payload() raises ValueError for invalid payload."""
        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "invalid",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )
        with pytest.raises(ValueError):
            signal.validate_payload(registry)

    def test_validate_unknown_type_passes_through(self, expires_soon):
        """validate_payload() passes through unknown types."""
        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="future_signal_type",
            payload={"custom": "data"},
            expires_at=expires_soon,
        )
        validated = signal.validate_payload(registry)
        assert validated == {"custom": "data"}


class TestSignalBusPublish:
    """Test SignalBus.publish() validation and coercion."""

    @pytest.mark.asyncio
    async def test_publish_validates_payload(self, expires_soon):
        """publish() validates and coerces payload before delivery."""
        bus = SignalBus()
        received_signals = []

        async def subscriber(signal: AgentSignal):
            received_signals.append(signal)

        bus.subscribe(subscriber)

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )

        await bus.publish(signal)

        assert len(received_signals) == 1
        received = received_signals[0]
        assert received.payload["expected_return"] == 0.0
        assert received.payload["symbol"] == "BTC/USD"

    @pytest.mark.asyncio
    async def test_publish_rejects_invalid_payload(self, expires_soon):
        """publish() raises ValueError for invalid payload on known type."""
        bus = SignalBus()

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "invalid",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )

        with pytest.raises(ValueError):
            await bus.publish(signal)

    @pytest.mark.asyncio
    async def test_publish_with_custom_registry(self, expires_soon):
        """publish() uses custom registry if provided."""
        custom_reg = SignalTypeRegistry()
        custom_reg.register("bittensor_consensus", BittensorConsensusPayload)

        bus = SignalBus(signal_registry=custom_reg)
        received_signals = []

        async def subscriber(signal: AgentSignal):
            received_signals.append(signal)

        bus.subscribe(subscriber)

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )

        await bus.publish(signal)

        assert len(received_signals) == 1
        assert received_signals[0].payload["symbol"] == "BTC/USD"

    @pytest.mark.asyncio
    async def test_publish_unknown_type_passes_through(self, expires_soon):
        """publish() allows unknown signal types through."""
        bus = SignalBus()
        received_signals = []

        async def subscriber(signal: AgentSignal):
            received_signals.append(signal)

        bus.subscribe(subscriber)

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="future_signal_type",
            payload={"custom": "data"},
            expires_at=expires_soon,
        )

        await bus.publish(signal)

        assert len(received_signals) == 1
        assert received_signals[0].payload == {"custom": "data"}

    @pytest.mark.asyncio
    async def test_publish_multiple_subscribers(self, expires_soon):
        """publish() delivers to all subscribers."""
        bus = SignalBus()
        received_by_1 = []
        received_by_2 = []

        async def subscriber1(signal: AgentSignal):
            received_by_1.append(signal)

        async def subscriber2(signal: AgentSignal):
            received_by_2.append(signal)

        bus.subscribe(subscriber1)
        bus.subscribe(subscriber2)

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )

        await bus.publish(signal)

        assert len(received_by_1) == 1
        assert len(received_by_2) == 1

    @pytest.mark.asyncio
    async def test_publish_subscriber_exception_doesnt_break_bus(self, expires_soon):
        """publish() continues even if one subscriber raises."""
        bus = SignalBus()
        received_by_good = []

        async def bad_subscriber(signal: AgentSignal):
            raise RuntimeError("Subscriber error")

        async def good_subscriber(signal: AgentSignal):
            received_by_good.append(signal)

        bus.subscribe(bad_subscriber)
        bus.subscribe(good_subscriber)

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )

        await bus.publish(signal)

        assert len(received_by_good) == 1

    @pytest.mark.asyncio
    async def test_publish_stores_signal(self, expires_soon):
        """publish() stores signal in bus history."""
        bus = SignalBus()

        signal = AgentSignal(
            source_agent="test_agent",
            signal_type="bittensor_consensus",
            payload={
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.75,
                "miner_count": 5,
            },
            expires_at=expires_soon,
        )

        await bus.publish(signal)

        results = bus.query(signal_type="bittensor_consensus")
        assert len(results) == 1
        assert results[0].source_agent == "test_agent"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_payload_with_zero_values(self):
        """Payloads with zero values should validate correctly."""
        payload = {
            "symbol": "BTC/USD",
            "timeframe": "1h",
            "direction": "long",
            "confidence": 0.0,
            "miner_count": 1,
        }
        model = BittensorConsensusPayload.model_validate(payload)
        assert model.confidence == 0.0

    def test_payload_with_extreme_floats(self):
        """Payloads with extreme float values."""
        payload = {
            "ticker": "BTC",
            "magnitude": 1000000.5,
            "volume": 0.0,
            "avg_volume": 0.0,
            "direction": "bullish",
        }
        model = VolumeAnomalyPayload.model_validate(payload)
        assert model.magnitude == 1000000.5

    def test_payload_with_empty_strings(self):
        """Payloads with empty strings should validate."""
        payload = {
            "symbol": "BTC/USD",
            "reason": "",
            "urgency": "low",
        }
        model = CloseSignalPayload.model_validate(payload)
        assert model.reason == ""

    def test_payload_with_long_strings(self):
        """Payloads with very long strings."""
        long_headline = "A" * 10000
        payload = {
            "ticker": "AAPL",
            "headline": long_headline,
            "sentiment": 0.5,
            "confidence": 0.8,
            "direction": "long",
        }
        model = NewsEventPayload.model_validate(payload)
        assert len(model.headline) == 10000

    def test_registry_validate_all_types(self):
        """Validate at least one payload for each registered type."""
        test_payloads = {
            "bittensor_miner_position": {
                "miner_hotkey": "test",
                "symbol": "BTC/USD",
                "direction": "long",
            },
            "bittensor_consensus": {
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.5,
                "miner_count": 1,
            },
            "intel_enriched_consensus": {
                "symbol": "BTC/USD",
                "timeframe": "1h",
                "direction": "long",
                "confidence": 0.5,
                "miner_count": 1,
                "enriched_confidence": 0.6,
            },
            "regime_update": {"market_phase": "expansion"},
            "news_event": {
                "ticker": "AAPL",
                "headline": "News",
                "sentiment": 0.5,
                "confidence": 0.8,
                "direction": "long",
            },
            "volume_anomaly": {
                "ticker": "BTC",
                "magnitude": 2.5,
                "volume": 1000,
                "avg_volume": 500,
                "direction": "bullish",
            },
            "price_dislocation": {
                "ticker": "BTC",
                "move_pct": 5.0,
                "prev_price": 40000,
                "current_price": 42000,
                "direction": "bullish",
            },
            "sentiment_spike": {
                "ticker": "BTC",
                "bullish_count": 100,
                "bearish_count": 20,
                "imbalance": 0.6,
                "direction": "bullish",
            },
            "spread_convergence": {
                "pair": "BTC/USD",
                "spread_bps": 5.0,
                "threshold_bps": 10.0,
            },
            "close": {"symbol": "BTC/USD"},
        }

        for signal_type, payload in test_payloads.items():
            result = registry.validate(signal_type, payload)
            assert isinstance(result, dict)
            assert result is not None
