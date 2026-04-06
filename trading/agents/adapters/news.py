from __future__ import annotations

import logging
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from agents.models import AgentSignal
from agents.signal_adapter import SignalAdapter

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)


class NewsAdapter(SignalAdapter):
    """LLM-based headline sentiment analysis. Requires ANTHROPIC_API_KEY."""

    def __init__(self, data_bus: DataBus, llm: Any = None) -> None:
        self._data_bus = data_bus
        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()

    def source_name(self) -> str:
        return "news"

    async def poll(self) -> list[AgentSignal]:

        signals: list[AgentSignal] = []
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=2)

        # In a real implementation, we would fetch from a news source (e.g. NewsAPI)
        # For Phase 1, we check if the DataBus has any news sources configured
        news_source = getattr(self._data_bus, "_news_source", None)
        if not news_source:
            logger.debug("NewsAdapter: No news source found on DataBus.")
            return []

        try:
            # Assume the news_source has a get_headlines method
            # This is a placeholder for actual source integration
            headlines = await news_source.get_headlines(limit=10)
            if not headlines:
                return []

            for item in headlines:
                sentiment = await self._analyze_headline(item["text"])
                if sentiment and sentiment.get("confidence", 0) > 0.7:
                    signals.append(
                        AgentSignal(
                            source_agent=self.source_name(),
                            signal_type="news_event",
                            payload={
                                "ticker": item.get("ticker"),
                                "headline": item["text"],
                                "sentiment": sentiment["label"],
                                "confidence": sentiment["confidence"],
                                "direction": "bullish"
                                if sentiment["label"] == "positive"
                                else "bearish",
                                "source": item.get("source", "newsapi"),
                            },
                            expires_at=expires,
                        )
                    )
        except Exception as e:
            logger.error("NewsAdapter: failed to poll news: %s", e)

        return signals

    async def _analyze_headline(self, headline: str) -> dict | None:
        """Analyze headline sentiment using LLM chain."""
        try:
            prompt = (
                f'Analyze the sentiment of this financial headline for the primary ticker mentioned: "{headline}"\n'
                'Respond in JSON format: {"label": "positive"|"negative"|"neutral", "confidence": 0.0-1.0}'
            )
            result = await self._llm.complete(prompt, max_tokens=100)
            content = result.text or ""

            # Basic JSON extraction from response text
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            return None
        except Exception as e:
            logger.debug("NewsAdapter: analysis error for '%s': %s", headline, e)
            return None
