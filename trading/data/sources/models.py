"""Shared data models for news sources."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


NEWS_SIGNAL_TOPIC = "NEWS_SIGNAL"


@dataclass
class NewsSignal:
    contract_ticker: str
    headline: str
    url: str
    published_at: datetime
    relevance: float        # 0.0–1.0
    sentiment: str          # "bullish_yes" | "bearish_yes" | "neutral"
    mispricing_score: float  # -1.0 to +1.0, positive = YES underpriced
    scored_at: datetime
