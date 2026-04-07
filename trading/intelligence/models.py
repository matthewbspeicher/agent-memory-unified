from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IntelReport:
    """Standardized output from any intelligence provider."""

    source: str          # "on_chain", "sentiment", "anomaly"
    symbol: str          # "BTCUSD"
    timestamp: datetime
    score: float         # -1.0 to +1.0 (bearish to bullish)
    confidence: float    # 0.0 to 1.0
    veto: bool           # True = hard block this trade
    veto_reason: str | None
    details: dict        # source-specific data


@dataclass
class IntelEnrichment:
    """Result of confidence enrichment calculation."""

    vetoed: bool
    veto_reason: str | None = None
    base_confidence: float = 0.0
    adjustment: float = 0.0
    final_confidence: float = 0.0
    contributions: list[dict] = field(default_factory=list)


@dataclass
class IntelRecord:
    """Stored for backtesting and analysis."""

    symbol: str
    timestamp: datetime
    provider: str
    report: IntelReport
    latency_ms: int
