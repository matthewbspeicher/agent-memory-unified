"""
NewsAPISource — fetches top headlines from NewsAPI.org and scores each
against open Kalshi contracts using a fallback-chain LLM client
(Anthropic → Groq → Ollama → rule-based).

Published to DataBus as event type "NEWS_SIGNAL".

Config (passed to __init__):
  api_key           — NewsAPI key (STA_NEWSAPI_KEY)
  anthropic_key     — Anthropic API key (STA_ANTHROPIC_API_KEY)
  groq_key          — Groq API key (STA_GROQ_API_KEY) — free tier fallback
  ollama_url        — Ollama base URL (STA_OLLAMA_BASE_URL) — local fallback
  fetch_interval    — seconds between fetches (default: 900 = 15 min)
  page_size         — max articles per query (default: 20)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

from data.sources.models import NEWS_SIGNAL_TOPIC, NewsSignal  # noqa: F401
from llm.client import LLMClient

NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"


class NewsAPISource:
    """
    Fetches headlines from NewsAPI and scores them against Kalshi contracts.

    Usage (wired in api/app.py):
        source = NewsAPISource(
            api_key=settings.newsapi_key,
            llm_client=llm_client,
        )
        asyncio.create_task(source.run(kalshi_source=data_bus._kalshi_source, event_bus=event_bus))
    """

    def __init__(
        self,
        api_key: str,
        llm_client: LLMClient | None = None,
        fetch_interval: int = 900,
        page_size: int = 20,
    ) -> None:
        self._api_key = api_key
        self._fetch_interval = fetch_interval
        self._page_size = page_size

        if llm_client is not None:
            self._llm = llm_client
        else:
            self._llm = LLMClient()

    async def _fetch_headlines(
        self, query: str = "finance economics politics"
    ) -> list[dict]:
        """Return list of raw article dicts from NewsAPI."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    NEWSAPI_URL,
                    params={
                        "q": query,
                        "apiKey": self._api_key,
                        "pageSize": self._page_size,
                        "language": "en",
                    },
                )
                resp.raise_for_status()
            return resp.json().get("articles", [])
        except Exception as exc:
            logger.warning("NewsAPISource._fetch_headlines failed: %s", exc)
            return []

    async def _score_headline(
        self,
        contract_ticker: str,
        contract_title: str,
        headline: str,
        url: str,
        published_at: datetime,
    ) -> NewsSignal | None:
        try:
            result = await self._llm.score_headline(contract_title, headline)
            return NewsSignal(
                contract_ticker=contract_ticker,
                headline=headline,
                url=url,
                published_at=published_at,
                relevance=result.relevance,
                sentiment=result.sentiment,
                mispricing_score=result.mispricing_score,
                scored_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning("Score headline failed: %s", exc)
            return None

    async def run(self, kalshi_source: Any, event_bus: Any) -> None:
        """Long-running loop: fetch → score → publish. Call via asyncio.create_task()."""
        while True:
            try:
                await self._tick(kalshi_source, event_bus)
            except Exception as exc:
                logger.error("NewsAPISource.run tick failed: %s", exc)
            await asyncio.sleep(self._fetch_interval)

    async def _tick(self, kalshi_source: Any, event_bus: Any) -> None:
        contracts = await kalshi_source.get_markets(status="open", max_pages=2)
        if not contracts:
            return

        articles = await self._fetch_headlines()
        if not articles:
            return

        for contract in contracts[:30]:  # cap at 30 contracts per tick
            for article in articles[:10]:  # cap at 10 headlines per contract
                title = article.get("title", "")
                url = article.get("url", "")
                published_raw = article.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(
                        published_raw.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    published_at = datetime.now(timezone.utc)

                signal = await self._score_headline(
                    contract_ticker=contract.ticker,
                    contract_title=contract.title,
                    headline=title,
                    url=url,
                    published_at=published_at,
                )
                if signal is not None:
                    await event_bus.publish(NEWS_SIGNAL_TOPIC, signal)
