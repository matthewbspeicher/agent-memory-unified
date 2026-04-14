"""Typed signal contracts for the SignalBus.

Every signal_type flowing through the bus now has a Pydantic model that
validates its payload at publish time.  The SignalTypeRegistry maps
signal_type strings to their corresponding model classes, so the bus
can validate any signal before it reaches subscribers.

Adding a new signal type:
    1. Define a Pydantic model inheriting from SignalPayload
    2. Call registry.register("your_type", YourModel)

The registry is pre-loaded with all known signal types at module import.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class SignalPayload(BaseModel):
    """Base for all typed signal payloads.  Every concrete payload must
    inherit from this and add its own fields."""

    model_config = {"extra": "allow"}  # allow unknown fields for extensibility


# ---------------------------------------------------------------------------
# Bittensor signals
# ---------------------------------------------------------------------------


class BittensorMinerPositionPayload(SignalPayload):
    """Payload for `signal_type="bittensor_miner_position"`.

    Emitted by TaoshiBridge / TaoshiSignalReplay when a miner opens,
    updates, or closes a position on Subnet 8.
    """

    miner_hotkey: str
    symbol: str
    direction: Literal["long", "short", "flat"]
    leverage: float = 0.0
    price: float = 0.0
    position_uuid: str = ""
    order_type: str = "FLAT"
    open_ms: int = 0
    signal_reason: str = "new_position"
    order_count: int = 1


class BittensorConsensusPayload(SignalPayload):
    """Payload for `signal_type="bittensor_consensus"`.

    Emitted by the consensus aggregator after merging miner predictions
    into a single directional signal.
    """

    symbol: str
    timeframe: str
    direction: Literal["long", "short", "flat"]
    confidence: float = Field(ge=0.0, le=1.0)
    expected_return: float = 0.0
    window_id: str = ""
    miner_count: int = Field(ge=1)


class IntelContribution(BaseModel):
    """Single intelligence-layer adjustment entry."""

    source: str
    adjustment: float = 0.0
    reason: str = ""


class IntelEnrichedConsensusPayload(BittensorConsensusPayload):
    """Payload for `signal_type="intel_enriched_consensus"`.

    Extends the base consensus signal with intelligence-layer enrichment
    (veto, confidence adjustments, contribution breakdown).
    """

    enriched_confidence: float = Field(ge=0.0, le=1.0)
    vetoed: bool = False
    intel: dict = Field(
        default_factory=dict
    )  # {veto_reason, base_confidence, adjustment, contributions}


# ---------------------------------------------------------------------------
# Market data signals
# ---------------------------------------------------------------------------


class RegimeUpdatePayload(SignalPayload):
    """Payload for `signal_type="regime_update"`.

    Emitted by the regime manager when market regime changes.
    """

    market_phase: str = "unknown"
    volatility: str = "normal"
    trend: str = "neutral"
    regime: str = "unknown"  # free-form for now; tighten later


class NewsEventPayload(SignalPayload):
    """Payload for `signal_type="news_event"`.

    Emitted by the news adapter when a significant news story is detected.
    """

    ticker: str
    headline: str
    sentiment: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    direction: Literal["long", "short", "neutral"]
    source: str = ""


class VolumeAnomalyPayload(SignalPayload):
    """Payload for `signal_type="volume_anomaly"`.

    Emitted when trading volume deviates significantly from the moving
    average for a given ticker.
    """

    ticker: str
    magnitude: float = Field(gt=0)
    volume: float = Field(ge=0)
    avg_volume: float = Field(ge=0)
    direction: Literal["bullish", "bearish", "neutral"]
    source: str = ""


class PriceDislocationPayload(SignalPayload):
    """Payload for `signal_type="price_dislocation"`.

    Emitted when price moves sharply relative to recent history.
    """

    ticker: str
    move_pct: float
    prev_price: float = Field(ge=0)
    current_price: float = Field(ge=0)
    direction: Literal["bullish", "bearish", "neutral"]
    source: str = ""


class SentimentSpikePayload(SignalPayload):
    """Payload for `signal_type="sentiment_spike"`.

    Emitted when Twitter/social sentiment exceeds normal bounds.
    """

    ticker: str
    bullish_count: int = Field(ge=0)
    bearish_count: int = Field(ge=0)
    imbalance: float = Field(ge=-1.0, le=1.0)
    direction: Literal["bullish", "bearish", "neutral"]
    source: str = ""


class SpreadConvergencePayload(SignalPayload):
    """Payload for `signal_type="spread_convergence"`.

    Emitted by the arbitrage adapter when a spread narrows.
    """

    pair: str
    spread_bps: float
    threshold_bps: float
    direction: Literal["narrowing", "widening", "stable"] = "narrowing"


class CloseSignalPayload(SignalPayload):
    """Payload for `signal_type="close"`.

    Emitted by the risk evaluator or exit manager to signal position
    closure.
    """

    symbol: str
    reason: str = ""
    urgency: Literal["low", "medium", "high"] = "medium"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SignalTypeRegistry:
    """Maps signal_type strings to their Pydantic payload models.

    Used by SignalBus.publish() to validate incoming signals before
    dispatching to subscribers.
    """

    def __init__(self) -> None:
        self._types: dict[str, type[SignalPayload]] = {}

    def register(self, signal_type: str, model: type[SignalPayload]) -> None:
        if signal_type in self._types and self._types[signal_type] is not model:
            logger.warning(
                "Overwriting signal type %r: %s → %s",
                signal_type,
                self._types[signal_type].__name__,
                model.__name__,
            )
        self._types[signal_type] = model

    def get(self, signal_type: str) -> type[SignalPayload] | None:
        return self._types.get(signal_type)

    def validate(self, signal_type: str, payload: dict) -> dict:
        """Validate *payload* against the registered model.

        Returns the validated dict (with defaults coerced) or raises
        ``ValueError`` on validation failure.

        Unknown signal types are allowed through with a warning so that
        new types can be introduced without a coordinated deploy.
        """
        model_cls = self._types.get(signal_type)
        if model_cls is None:
            logger.warning(
                "Unknown signal_type %r — payload not validated. "
                "Register a model with SignalTypeRegistry.register().",
                signal_type,
            )
            return payload
        try:
            instance = model_cls.model_validate(payload)
            return instance.model_dump()
        except ValidationError as exc:
            raise ValueError(
                f"Payload validation failed for signal_type={signal_type!r}: {exc}"
            ) from exc

    def known_types(self) -> list[str]:
        return sorted(self._types.keys())

    def __contains__(self, signal_type: str) -> bool:
        return signal_type in self._types


# ---------------------------------------------------------------------------
# Global registry — pre-loaded with all known types
# ---------------------------------------------------------------------------

registry = SignalTypeRegistry()

registry.register("bittensor_miner_position", BittensorMinerPositionPayload)
registry.register("bittensor_consensus", BittensorConsensusPayload)
registry.register("intel_enriched_consensus", IntelEnrichedConsensusPayload)
registry.register("regime_update", RegimeUpdatePayload)
registry.register("news_event", NewsEventPayload)
registry.register("volume_anomaly", VolumeAnomalyPayload)
registry.register("price_dislocation", PriceDislocationPayload)
registry.register("sentiment_spike", SentimentSpikePayload)
registry.register("spread_convergence", SpreadConvergencePayload)
registry.register("close", CloseSignalPayload)
