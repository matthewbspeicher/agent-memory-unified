"""
RSSNewsSource — polls a configurable list of RSS/Atom feed URLs in parallel,
deduplicates articles by URL hash, and scores headlines against open Kalshi
contracts using a fallback-chain LLM client (Anthropic → Groq → Ollama → rule-based).

Published to EventBus as event type "NEWS_SIGNAL".

Config (passed to __init__):
  feed_urls       — list of feed URLs (default: DEFAULT_FEEDS; empty list also uses DEFAULT_FEEDS)
  anthropic_key   — Anthropic API key (STA_ANTHROPIC_API_KEY)
  groq_key        — Groq API key (STA_GROQ_API_KEY) — free tier fallback
  ollama_url      — Ollama base URL (STA_OLLAMA_BASE_URL) — local fallback
  poll_interval   — seconds between polls (default: 90)
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

from data.sources.models import NEWS_SIGNAL_TOPIC, NewsSignal  # noqa: F401
from llm.client import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    # Business / Markets
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "http://feeds.marketwatch.com/marketwatch/topstories",
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://www.ft.com/?format=rss",
    # General / World News
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "http://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.theguardian.com/world/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
]

_DEDUP_TTL = timedelta(hours=24)
_MAX_SCORED_PER_TICK = 10


@dataclass
class Article:
    title: str
    url: str
    published_at: datetime
    source_name: str


class RSSNewsSource:
    """
    Polls RSS/Atom feeds in parallel, deduplicates, and scores headlines.

    Usage (wired in api/app.py):
        source = RSSNewsSource(anthropic_key=settings.anthropic_api_key, groq_key=settings.groq_api_key)
        asyncio.create_task(source.run(kalshi_source=data_bus._kalshi_source, event_bus=event_bus))
    """

    def __init__(
        self,
        feed_urls: list[str] | None = None,
        anthropic_key: str | None = None,
        groq_key: str | None = None,
        ollama_url: str = "http://localhost:11434",
        poll_interval: int = 90,
        llm_chain: list[str] | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._feed_urls: list[str] = feed_urls if feed_urls else DEFAULT_FEEDS
        self._poll_interval = poll_interval

        # Unified LLM client with fallback chain
        self._llm = llm_client or LLMClient(
            anthropic_key=anthropic_key,
            groq_key=groq_key,
            ollama_url=ollama_url,
            chain=llm_chain,
        )

        # url_hash -> first-seen timestamp
        self._seen_urls: dict[str, datetime] = {}
        # per-feed consecutive failure counter
        self._fail_counts: dict[str, int] = {}
        # cached articles from last successful tick
        self._latest_articles: list[Article] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_headlines(self, limit: int = 10) -> list[dict]:
        """Return up to *limit* cached articles as NewsAdapter-compatible dicts."""
        return [
            {
                "text": a.title,
                "url": a.url,
                "source": a.source_name,
                "ticker": None,
            }
            for a in self._latest_articles[:limit]
        ]

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    async def _fetch_all_feeds(self) -> list[Article]:
        """Fetch all configured feeds in parallel and return combined articles."""
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            results = await asyncio.gather(
                *[self._fetch_single_feed(client, url) for url in self._feed_urls],
                return_exceptions=True,
            )
        articles: list[Article] = []
        for result in results:
            if isinstance(result, list):
                articles.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Feed fetch raised: %s", result)
        return articles

    async def _fetch_single_feed(
        self, client: httpx.AsyncClient, feed_url: str
    ) -> list[Article]:
        """Fetch and parse a single RSS/Atom feed URL. Returns [] on any error."""
        try:
            resp = await client.get(feed_url)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
            articles = _parse_feed(parsed, feed_url)
            # Reset failure counter on success
            self._fail_counts[feed_url] = 0
            return articles
        except Exception as exc:
            count = self._fail_counts.get(feed_url, 0) + 1
            self._fail_counts[feed_url] = count
            if count >= 3:
                logger.error(
                    "RSSNewsSource: feed %s failed %d times: %s", feed_url, count, exc
                )
            else:
                logger.warning(
                    "RSSNewsSource: feed %s failed (%d): %s", feed_url, count, exc
                )
            return []

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _evict_stale(self) -> None:
        """Remove seen-URL entries older than 24 hours (lazy eviction)."""
        cutoff = datetime.now(timezone.utc) - _DEDUP_TTL
        stale = [h for h, ts in self._seen_urls.items() if ts < cutoff]
        for h in stale:
            del self._seen_urls[h]

    def _dedup(self, articles: list[Article]) -> list[Article]:
        """Return only articles whose URL has not been seen before; record new ones."""
        fresh: list[Article] = []
        now = datetime.now(timezone.utc)
        for article in articles:
            url_hash = hashlib.sha256(article.url.encode()).hexdigest()[:16]
            if url_hash not in self._seen_urls:
                self._seen_urls[url_hash] = now
                fresh.append(article)
        return fresh

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    async def _score_headline(
        self,
        contract_ticker: str,
        contract_title: str,
        headline: str,
        url: str,
        published_at: datetime,
    ) -> NewsSignal | None:
        """Score a single headline against a contract using fallback-chain LLM."""
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

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self, kalshi_source: Any, event_bus: Any) -> None:
        """Long-running loop: tick → sleep. Call via asyncio.create_task()."""
        while True:
            try:
                await self._tick(kalshi_source, event_bus)
            except Exception as exc:
                logger.error("RSSNewsSource.run tick failed: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _tick(self, kalshi_source: Any, event_bus: Any) -> None:
        """One poll cycle: evict → fetch → dedup → cache → score → publish."""
        self._evict_stale()

        articles = await self._fetch_all_feeds()
        fresh = self._dedup(articles)
        if fresh:
            self._latest_articles = fresh + self._latest_articles
            # Keep cache bounded (newest first, max 200)
            self._latest_articles = self._latest_articles[:200]

        contracts = await kalshi_source.get_markets(status="open", max_pages=2)
        if not contracts or not fresh:
            return

        scored = 0
        for article in fresh:
            if scored >= _MAX_SCORED_PER_TICK:
                break
            for contract in contracts[:30]:
                signal = await self._score_headline(
                    contract_ticker=contract.ticker,
                    contract_title=contract.title,
                    headline=article.title,
                    url=article.url,
                    published_at=article.published_at,
                )
                if signal is not None:
                    await event_bus.publish(NEWS_SIGNAL_TOPIC, signal)
            scored += 1


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_feed(parsed: Any, feed_url: str) -> list[Article]:
    """Convert a feedparser result into a list of Article objects."""
    feed_title: str = getattr(parsed.feed, "title", feed_url)
    articles: list[Article] = []

    for entry in parsed.entries:
        title: str = getattr(entry, "title", "").strip()
        if not title:
            continue

        # URL: prefer 'link', fall back to 'id'
        url: str = getattr(entry, "link", "") or getattr(entry, "id", "")
        if not url:
            continue

        # Published timestamp
        published_at = _parse_published(entry)

        articles.append(
            Article(
                title=title,
                url=url,
                published_at=published_at,
                source_name=feed_title,
            )
        )

    return articles


def _parse_published(entry: Any) -> datetime:
    """Extract and normalise the published timestamp from a feedparser entry."""
    # feedparser provides parsed_time tuples via published_parsed / updated_parsed
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t is not None:
            try:
                ts = calendar.timegm(t)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass

    # Fall back to raw string fields
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

    return datetime.now(timezone.utc)
