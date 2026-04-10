# trading/competition/tracker.py
"""Subscribes to SignalBus and buffers signals for hourly match processing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Signal types that represent tradeable opportunities
TRACKABLE_SIGNAL_TYPES = {
    "opportunity",
    "bittensor_consensus",
    "intel_enriched_consensus",
}


@dataclass
class TrackedSignal:
    source_agent: str
    asset: str
    direction: str  # "long" | "short" | "close"
    confidence: float
    timestamp: datetime
    payload: dict = field(default_factory=dict)


class SignalTracker:
    """Collects signals from SignalBus for competition match processing."""

    def __init__(self) -> None:
        self.pending_signals: list[TrackedSignal] = []

    async def on_signal(self, signal: Any) -> None:
        """SignalBus callback — filter and buffer relevant signals."""
        if signal.signal_type not in TRACKABLE_SIGNAL_TYPES:
            return

        payload = signal.payload or {}
        symbol = payload.get("symbol", "")
        direction = payload.get("direction") or payload.get("signal", "")
        confidence = signal.confidence or payload.get("confidence", 0.5)

        if not symbol or not direction:
            return

        asset = self._normalize_asset(symbol)
        tracked = TrackedSignal(
            source_agent=signal.source_agent,
            asset=asset,
            direction=str(direction),
            confidence=float(confidence),
            timestamp=signal.timestamp,
            payload=payload,
        )
        self.pending_signals.append(tracked)
        logger.debug(
            "competition.tracker: buffered signal from %s on %s",
            signal.source_agent,
            asset,
        )

    def drain(self) -> list[TrackedSignal]:
        """Return all pending signals and clear the buffer."""
        signals = self.pending_signals[:]
        self.pending_signals.clear()
        return signals

    def _normalize_asset(self, symbol: str) -> str:
        """BTCUSD -> BTC, BTC/USDT -> BTC, ETHUSD -> ETH."""
        cleaned = re.sub(r"[/\-]?(USD[T]?|USDT)$", "", symbol.upper())
        return cleaned
