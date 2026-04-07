from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from agents.models import AgentSignal
from agents.signal_adapter import SignalAdapter

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)

TICKER_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Word-boundary patterns to avoid substring false positives
BULLISH_PATTERNS = [
    re.compile(r"\b" + w + r"\b")
    for w in ["buy", "bull", "bullish", "long", "calls", "moon"]
]
BEARISH_PATTERNS = [
    re.compile(r"\b" + w + r"\b")
    for w in ["sell", "bear", "bearish", "short", "puts", "crash"]
]


class TwitterAdapter(SignalAdapter):
    """Twitter/X sentiment via opencli-rs. Requires opencli-rs in PATH."""

    def __init__(self, data_bus: DataBus, sentiment_threshold: int = 3) -> None:
        self._data_bus = data_bus
        self._sentiment_threshold = sentiment_threshold

    def source_name(self) -> str:
        return "twitter"

    async def poll(self) -> list[AgentSignal]:
        signals: list[AgentSignal] = []
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=60)

        # Get top tickers from Kalshi to scout
        try:
            markets = await self._data_bus.get_kalshi_markets()
            tickers = [
                m.ticker
                for m in markets[:5]
                if TICKER_PATTERN.match(m.ticker or "")
            ]
        except Exception as e:
            logger.error("TwitterAdapter: failed to get tickers from DataBus: %s", e)
            return []

        for ticker in tickers:
            tweets = self._scout_ticker(ticker)
            if not tweets:
                continue

            sentiment = self._analyze_sentiment(ticker, tweets)
            if sentiment["imbalance"] >= self._sentiment_threshold:
                signals.append(
                    AgentSignal(
                        source_agent=self.source_name(),
                        signal_type="sentiment_spike",
                        payload={
                            "ticker": ticker,
                            "bullish_count": sentiment["bullish"],
                            "bearish_count": sentiment["bearish"],
                            "imbalance": sentiment["imbalance"],
                            "direction": "bullish"
                            if sentiment["bullish"] > sentiment["bearish"]
                            else "bearish",
                            "source": "twitter",
                        },
                        expires_at=expires,
                    )
                )

        return signals

    def _scout_ticker(self, ticker: str) -> list[dict] | None:
        """Run opencli-rs to get sentiment for a ticker."""
        try:
            cmd = [
                "opencli-rs",
                "twitter",
                "search",
                "--query",
                ticker,
                "--format",
                "json",
                "--limit",
                "10",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.debug("opencli-rs failed for %s: %s", ticker, result.stderr)
                return None
            return json.loads(result.stdout)
        except Exception as e:
            logger.debug("TwitterAdapter: scout error for %s: %s", ticker, e)
            return None

    def _analyze_sentiment(self, ticker: str, tweets: list[dict]) -> dict:
        """Correlate sentiment with word-boundary matching."""
        text = " ".join([str(t.get("text", "")).lower() for t in tweets])
        bullish = sum(len(p.findall(text)) for p in BULLISH_PATTERNS)
        bearish = sum(len(p.findall(text)) for p in BEARISH_PATTERNS)

        return {
            "bullish": bullish,
            "bearish": bearish,
            "imbalance": abs(bullish - bearish),
        }
