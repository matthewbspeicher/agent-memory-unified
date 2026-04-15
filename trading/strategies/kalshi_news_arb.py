"""
KalshiNewsArbAgent — News Arbitrage strategy for Kalshi prediction markets.

Scan flow:
1. Fetch open Kalshi markets in configured categories
2. For each market above min_volume, fetch recent RSS headlines
3. Prompt an LLM to estimate the probability given the headlines
4. Emit an Opportunity when |llm_prob - market_price| > threshold

agents.yaml config example:
  - name: kalshi_news_arb
    strategy: kalshi_news_arb
    schedule: cron
    cron: "*/15 * * * *"
    action_level: suggest_trade
    parameters:
      categories: ["economics", "climate"]
      rss_feeds:
        - https://feeds.reuters.com/reuters/topNews
      threshold_cents: 15
      max_markets_per_scan: 30
      min_volume: 200
      min_confidence: 60
      min_days_to_close: 1
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from agents.base import StructuredAgent
from agents.models import Opportunity, OpportunityStatus
from broker.models import LimitOrder, OrderSide, TIF
from llm.client import LLMClient

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)


async def _fetch_headlines(rss_url: str, limit: int = 5) -> list[str]:
    """Fetch and parse an RSS feed, returning the most recent headlines."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(rss_url, follow_redirects=True)
            resp.raise_for_status()
        root = ET.fromstring(resp.text)
        headlines: list[str] = []
        for item in root.iter("item"):
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                headlines.append(title_el.text.strip())
            if len(headlines) >= limit:
                break
        return headlines
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", rss_url, exc)
        return []


async def _fetch_newsapi_headlines(
    query: str, newsapi_key: str, page_size: int = 5
) -> list[str]:
    """Fetch top headlines from NewsAPI for a given query."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://newsapi.org/v2/top-headlines",
                params={"q": query, "apiKey": newsapi_key, "pageSize": page_size},
            )
            resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [a["title"] for a in articles if a.get("title")]
    except Exception as exc:
        logger.warning("NewsAPI fetch failed for query '%s': %s", query, exc)
        return []


async def _llm_estimate_probability(
    question: str,
    headlines: list[str],
    llm_client: LLMClient,
) -> tuple[float, int, str] | None:
    """
    Use the unified LLM client to estimate probability.

    Returns (probability_0_to_1, confidence_0_to_100, reasoning) or None on failure.
    """
    try:
        result = await llm_client.estimate_probability(question, headlines)
        return result.implied_probability, result.confidence, result.reasoning
    except Exception as exc:
        logger.warning("LLM probability estimate failed: %s", exc)
        return None


class KalshiNewsArbAgent(StructuredAgent):
    description = (
        "Scans Kalshi prediction markets and uses an LLM to estimate the "
        "fair probability from recent news. Emits opportunities when the LLM "
        "estimate differs from the market price by more than threshold_cents."
    )

    async def scan(self, data: DataBus) -> list[Opportunity]:
        params = self.parameters
        categories: list[str] = params.get("categories", ["economics"])
        rss_feeds: list[str] = params.get("rss_feeds", [])
        threshold: int = int(params.get("threshold_cents", 15))
        max_markets: int = int(params.get("max_markets_per_scan", 30))
        min_volume: int = int(params.get("min_volume", 100))
        min_confidence: int = int(params.get("min_confidence", 60))
        min_days_to_close: float = float(params.get("min_days_to_close", 0))

        now = datetime.now(timezone.utc)

        # Requires KalshiDataSource attached to DataBus
        kalshi_source = getattr(data, "_kalshi_source", None)
        if kalshi_source is None:
            logger.warning("%s: no KalshiDataSource on DataBus — skipping", self.name)
            return []

        # Build unified LLM client from DataBus settings
        anthropic_key = getattr(data, "_anthropic_key", None)
        _settings = getattr(data, "_settings", None)
        groq_key = getattr(_settings, "groq_api_key", None) if _settings else None
        ollama_url = (
            getattr(_settings, "ollama_base_url", "http://localhost:11434")
            if _settings
            else "http://localhost:11434"
        )

        llm_client = LLMClient(
            anthropic_key=anthropic_key,
            groq_key=groq_key,
            ollama_url=ollama_url,
        )

        # Gather headlines once for all markets
        # Prefer NewsAPI if key is configured; fall back to RSS feeds
        newsapi_key: str | None = params.get("newsapi_key") or None
        if not newsapi_key and _settings is not None:
            newsapi_key = getattr(_settings, "newsapi_key", None) or None

        all_headlines: list[str] = []
        if newsapi_key:
            all_headlines = await _fetch_newsapi_headlines(
                "markets finance", newsapi_key, page_size=15
            )
        # Fall back to RSS if NewsAPI returned nothing (or wasn't configured).
        # NewsAPI has been known to silently yield [] on rate-limit / outage.
        if not all_headlines:
            for feed in rss_feeds:
                all_headlines.extend(await _fetch_headlines(feed, limit=5))
        all_headlines = all_headlines[:15]  # cap total context

        opportunities: list[Opportunity] = []
        for category in categories:
            markets = await kalshi_source.get_markets(category=category)
            markets = [
                m
                for m in markets
                if m.volume_24h >= min_volume and m.mid_probability is not None
            ]
            markets.sort(key=lambda m: m.volume_24h, reverse=True)
            markets = markets[:max_markets]

            for contract in markets:
                market_prob = contract.mid_probability
                if market_prob is None:
                    continue

                # Filter markets closing too soon
                if min_days_to_close > 0:
                    days_left_pre = (contract.close_time - now).total_seconds() / 86400
                    if days_left_pre < min_days_to_close:
                        continue

                result = await _llm_estimate_probability(
                    question=contract.title,
                    headlines=all_headlines,
                    llm_client=llm_client,
                )
                if result is None:
                    continue
                llm_prob, confidence, llm_reasoning = result

                # Skip if LLM is not confident enough
                if confidence < min_confidence:
                    logger.debug(
                        "%s: skipping %s — LLM confidence %d < min_confidence %d",
                        self.name,
                        contract.ticker,
                        confidence,
                        min_confidence,
                    )
                    continue

                gap_cents = abs(round((llm_prob - float(market_prob)) * 100))

                if gap_cents < threshold:
                    continue

                direction = "YES" if llm_prob > float(market_prob) else "NO"
                side = OrderSide.BUY if direction == "YES" else OrderSide.SELL

                # Suggest a limit order 1 cent inside the gap
                limit_prob = Decimal(str(round(market_prob, 2)))
                adjustment = Decimal("0.01") * (1 if direction == "YES" else -1)
                limit_price = max(
                    Decimal("0.01"), min(Decimal("0.99"), limit_prob + adjustment)
                )

                symbol = contract.as_symbol
                suggested = LimitOrder(
                    symbol=symbol,
                    side=side,
                    quantity=Decimal("10"),
                    account_id="KALSHI",
                    limit_price=limit_price,
                    time_in_force=TIF.GTC,
                )

                days_left = (contract.close_time - now).total_seconds() / 86400
                opportunities.append(
                    Opportunity(
                        id=str(uuid.uuid4()),
                        agent_name=self.name,
                        symbol=symbol,
                        signal=direction,
                        confidence=round((confidence / 100) * (gap_cents / 100), 3),
                        reasoning=(
                            f"Market: {market_prob:.0%} | LLM: {llm_prob:.0%} | "
                            f"Gap: {gap_cents}¢ | Conf: {confidence}\n"
                            f"Q: {contract.title}\n{llm_reasoning}"
                        ),
                        data={
                            "category": contract.category,
                            "market_prob": float(market_prob),
                            "llm_prob": llm_prob,
                            "llm_confidence": confidence,
                            "gap_cents": gap_cents,
                            "volume_24h": contract.volume_24h,
                            "days_to_close": round(days_left, 2),
                            "close_time": contract.close_time.isoformat(),
                        },
                        timestamp=now,
                        suggested_trade=suggested,
                        status=OpportunityStatus.PENDING,
                    )
                )

        return opportunities
