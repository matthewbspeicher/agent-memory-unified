# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from pydantic import ValidationError

from agents.models import AgentSignal
from data.signal_types import (
    BittensorConsensusPayload,
    BittensorMinerPositionPayload,
    CloseSignalPayload,
    IntelEnrichedConsensusPayload,
    NewsEventPayload,
    PriceDislocationPayload,
    RegimeUpdatePayload,
    SentimentSpikePayload,
    SignalPayload,
    SignalTypeRegistry,
    SpreadConvergencePayload,
    VolumeAnomalyPayload,
    registry,
)

PayloadDict = dict[str, object]


VALID_MODEL_CASES: list[tuple[type[SignalPayload], PayloadDict]] = [
    (
        BittensorMinerPositionPayload,
        {
            "miner_hotkey": "5GminerHotkey",
            "symbol": "AAPL",
            "direction": "long",
        },
    ),
    (
        BittensorConsensusPayload,
        {
            "symbol": "AAPL",
            "timeframe": "15m",
            "direction": "short",
            "confidence": 0.73,
            "miner_count": 5,
        },
    ),
    (
        IntelEnrichedConsensusPayload,
        {
            "symbol": "MSFT",
            "timeframe": "1h",
            "direction": "flat",
            "confidence": 0.61,
            "miner_count": 3,
            "enriched_confidence": 0.82,
            "intel": {"veto_reason": "none", "adjustment": 0.1},
        },
    ),
    (
        RegimeUpdatePayload,
        {
            "market_phase": "risk_on",
            "volatility": "high",
            "trend": "up",
            "regime": "momentum",
        },
    ),
    (
        NewsEventPayload,
        {
            "ticker": "TSLA",
            "headline": "Positive delivery surprise",
            "sentiment": 0.8,
            "confidence": 0.9,
            "direction": "long",
            "source": "newswire",
        },
    ),
    (
        VolumeAnomalyPayload,
        {
            "ticker": "NVDA",
            "magnitude": 2.4,
            "volume": 1_500_000,
            "avg_volume": 550_000,
            "direction": "up",
            "source": "volume_monitor",
        },
    ),
    (
        PriceDislocationPayload,
        {
            "ticker": "AMZN",
            "move_pct": -3.5,
            "prev_price": 185.25,
            "current_price": 178.77,
            "direction": "down",
            "source": "price_monitor",
        },
    ),
    (
        SentimentSpikePayload,
        {
            "ticker": "BTC",
            "bullish_count": 120,
            "bearish_count": 12,
            "imbalance": 0.82,
            "direction": "bullish",
            "source": "social_feed",
        },
    ),
    (
        SpreadConvergencePayload,
        {
            "pair": "BTC/USD-ETH/USD",
            "spread_bps": 18.5,
            "threshold_bps": 25.0,
            "direction": "narrowing",
        },
    ),
    (
        CloseSignalPayload,
        {
            "symbol": "AAPL",
            "reason": "risk_limit",
            "urgency": "high",
        },
    ),
]

INVALID_MODEL_CASES: list[tuple[type[SignalPayload], PayloadDict, str]] = [
    (
        BittensorMinerPositionPayload,
        {"symbol": "AAPL", "direction": "long"},
        "missing required field",
    ),
    (
        BittensorMinerPositionPayload,
        {
            "miner_hotkey": "hk",
            "symbol": "AAPL",
            "direction": "long",
            "unexpected": True,
        },
        "extra field",
    ),
    (
        BittensorMinerPositionPayload,
        {
            "miner_hotkey": "hk",
            "symbol": "AAPL",
            "direction": "long",
            "open_ms": "not-an-int",
        },
        "wrong type",
    ),
    (
        BittensorConsensusPayload,
        {"symbol": "AAPL", "timeframe": "15m", "direction": "long"},
        "missing required field",
    ),
    (
        BittensorConsensusPayload,
        {
            "symbol": "AAPL",
            "timeframe": "15m",
            "direction": "long",
            "confidence": 1.25,
            "miner_count": 2,
        },
        "out of range float",
    ),
    (
        IntelEnrichedConsensusPayload,
        {
            "symbol": "AAPL",
            "timeframe": "15m",
            "direction": "short",
            "confidence": 0.4,
            "miner_count": 2,
            "enriched_confidence": 0.9,
            "extra": "nope",
        },
        "extra field",
    ),
    (
        IntelEnrichedConsensusPayload,
        {
            "symbol": "AAPL",
            "timeframe": "15m",
            "direction": "short",
            "confidence": "high",
            "miner_count": 2,
            "enriched_confidence": 0.9,
        },
        "wrong type",
    ),
    (
        RegimeUpdatePayload,
        {"market_phase": 1, "volatility": "high", "trend": "up", "regime": "trend"},
        "wrong type",
    ),
    (
        RegimeUpdatePayload,
        {
            "market_phase": "risk_on",
            "volatility": "high",
            "trend": "up",
            "regime": "trend",
            "unknown": "field",
        },
        "extra field",
    ),
    (
        NewsEventPayload,
        {
            "ticker": "TSLA",
            "headline": "Positive delivery surprise",
            "sentiment": 1.5,
            "confidence": 0.9,
            "direction": "long",
        },
        "out of range float",
    ),
    (
        NewsEventPayload,
        {
            "headline": "Missing ticker",
            "sentiment": 0.1,
            "confidence": 0.9,
            "direction": "neutral",
        },
        "missing required field",
    ),
    (
        VolumeAnomalyPayload,
        {
            "ticker": "NVDA",
            "magnitude": 0.0,
            "volume": 1_000,
            "avg_volume": 900,
            "direction": "up",
        },
        "out of range float",
    ),
    (
        VolumeAnomalyPayload,
        {
            "ticker": "NVDA",
            "magnitude": 2.0,
            "volume": "a lot",
            "avg_volume": 900,
            "direction": "up",
        },
        "wrong type",
    ),
    (
        PriceDislocationPayload,
        {
            "ticker": "AMZN",
            "move_pct": -3.5,
            "prev_price": -1.0,
            "current_price": 178.77,
            "direction": "down",
        },
        "out of range float",
    ),
    (
        PriceDislocationPayload,
        {
            "ticker": "AMZN",
            "move_pct": "large",
            "prev_price": 185.25,
            "current_price": 178.77,
            "direction": "down",
        },
        "wrong type",
    ),
    (
        SentimentSpikePayload,
        {
            "ticker": "BTC",
            "bullish_count": 120,
            "bearish_count": 12,
            "imbalance": 1.5,
            "direction": "bullish",
        },
        "out of range float",
    ),
    (
        SentimentSpikePayload,
        {
            "bullish_count": 120,
            "bearish_count": 12,
            "imbalance": 0.5,
            "direction": "bullish",
        },
        "missing required field",
    ),
    (
        SpreadConvergencePayload,
        {
            "pair": "BTC/USD-ETH/USD",
            "spread_bps": "tight",
            "threshold_bps": 25.0,
        },
        "wrong type",
    ),
    (
        SpreadConvergencePayload,
        {
            "pair": "BTC/USD-ETH/USD",
            "spread_bps": 18.5,
            "threshold_bps": 25.0,
            "direction": "sideways",
        },
        "literal value",
    ),
    (
        CloseSignalPayload,
        {"reason": "risk_limit", "urgency": "high"},
        "missing required field",
    ),
    (
        CloseSignalPayload,
        {"symbol": "AAPL", "reason": "risk_limit", "urgency": 1},
        "wrong type",
    ),
]


@pytest.mark.parametrize(
    "model_cls,payload",
    VALID_MODEL_CASES,
    ids=[cls.__name__ for cls, _ in VALID_MODEL_CASES],
)
def test_payload_models_accept_valid_data(
    model_cls: type[SignalPayload], payload: PayloadDict
):
    model = model_cls(**payload)
    assert isinstance(model, model_cls)


@pytest.mark.parametrize(
    "model_cls,payload,case",
    INVALID_MODEL_CASES,
    ids=[f"{cls.__name__}-{case}" for cls, _, case in INVALID_MODEL_CASES],
)
def test_payload_models_reject_invalid_data(
    model_cls: type[SignalPayload], payload: PayloadDict, _case: str
):
    with pytest.raises(ValidationError):
        _ = model_cls(**payload)


def test_signal_type_registry_validates_defaults_for_known_types():
    validated = cast(PayloadDict, registry.validate("bittensor_miner_position", {"miner_hotkey": "5GminerHotkey", "symbol": "AAPL", "direction": "flat"}))

    assert validated["leverage"] == 0.0
    assert validated["price"] == 0.0
    assert validated["position_uuid"] == ""
    assert validated["order_type"] == "FLAT"
    assert validated["open_ms"] == 0
    assert validated["signal_reason"] == "new_position"
    assert validated["order_count"] == 1


def test_signal_type_registry_passes_through_unknown_types():
    empty_registry = SignalTypeRegistry()
    payload: PayloadDict = {"whatever": [1, 2, 3], "nested": {"ok": True}}

    validated = cast(PayloadDict, empty_registry.validate("new_signal_type", payload))

    assert validated == payload


@pytest.mark.parametrize(
    "signal_type,payload",
    [
        (
            "bittensor_consensus",
            {
                "symbol": "AAPL",
                "timeframe": "15m",
                "direction": "long",
                "confidence": 1.25,
                "miner_count": 2,
            },
        ),
        (
            "news_event",
            {
                "ticker": "TSLA",
                "headline": "News",
                "sentiment": 1.2,
                "confidence": 0.9,
                "direction": "neutral",
            },
        ),
    ],
)
def test_signal_type_registry_raises_value_error_for_invalid_known_payloads(
    signal_type: str, payload: PayloadDict
):
    with pytest.raises(ValueError):
        registry.validate(signal_type, payload)


def test_agent_signal_validate_payload_works_with_default_registry():
    signal = AgentSignal(
        source_agent="alpha_agent",
        signal_type="bittensor_miner_position",
        payload={
            "miner_hotkey": "5GminerHotkey",
            "symbol": "AAPL",
            "direction": "long",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    validated = cast(PayloadDict, signal.validate_payload())

    assert validated["leverage"] == 0.0
    assert validated["order_count"] == 1


def test_agent_signal_validate_payload_works_with_explicit_registry():
    explicit_registry = SignalTypeRegistry()
    explicit_registry.register(
        "bittensor_miner_position", BittensorMinerPositionPayload
    )

    signal = AgentSignal(
        source_agent="beta_agent",
        signal_type="bittensor_miner_position",
        payload={
            "miner_hotkey": "5GminerHotkey",
            "symbol": "MSFT",
            "direction": "short",
            "leverage": "1.5",
            "order_count": "2",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    validated = cast(PayloadDict, signal.validate_payload(explicit_registry))

    assert validated["leverage"] == 1.5
    assert validated["order_count"] == 2


@pytest.mark.asyncio
async def test_signal_bus_publish_validates_and_coerces_payload_before_delivery():
    from data.signal_bus import SignalBus

    bus = SignalBus()
    received: list[AgentSignal] = []

    async def subscriber(signal: AgentSignal) -> None:
        received.append(signal)

    bus.subscribe(subscriber)

    signal = AgentSignal(
        source_agent="publisher",
        signal_type="bittensor_miner_position",
        payload={
            "miner_hotkey": "5GminerHotkey",
            "symbol": "AAPL",
            "direction": "flat",
            "leverage": "1.5",
            "price": "187.25",
            "order_count": "2",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    await bus.publish(signal)

    payload = cast(PayloadDict, signal.payload)
    assert payload["leverage"] == 1.5
    assert payload["price"] == 187.25
    assert payload["order_count"] == 2
    assert received == [signal]
    received_payload = cast(PayloadDict, received[0].payload)
    assert received_payload["order_type"] == "FLAT"
