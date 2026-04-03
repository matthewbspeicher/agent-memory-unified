"""
Polymarket News Arbitrage Agent.

Scans open Polymarket markets and compares market prices with LLM-derived
probabilities from recent RSS news headlines. Emits an Opportunity if the gap
exceeds `threshold_cents`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from agents.base import StructuredAgent
from agents.models import AgentConfig, Opportunity
from broker.models import LimitOrder, Symbol, OrderSide
from adapters.polymarket.data_source import PolymarketDataSource

logger = logging.getLogger(__name__)

class PolymarketNewsArbAgent(StructuredAgent):
    description = "News arbitrage matching LLMs against Polymarket CLOB feeds."
    def __init__(self, config: AgentConfig, settings=None, **kwargs):
        super().__init__(config, **kwargs)

        params = config.parameters or {}
        self.tags = params.get("tags", ["politics", "crypto"])
        self.rss_feeds = params.get("rss_feeds", [])
        self.threshold_cents = params.get("threshold_cents", 15)
        self.min_confidence = params.get("min_confidence", 60)
        self.min_volume = params.get("min_volume", 500)
        self.min_days = params.get("min_days_to_close", 1)
        self.max_markets = params.get("max_markets_per_scan", 30)
        # NewsAPI key: prefer agent params, fall back to global settings
        self.newsapi_key: str | None = params.get("newsapi_key") or None
        if not self.newsapi_key and settings is not None:
            self.newsapi_key = getattr(settings, "newsapi_key", None) or None

    async def scan(self, data) -> list[Opportunity]:
        app_state = getattr(self.config, "_app_state", None)
        if app_state and "polymarket" not in app_state.brokers:
            logger.debug("PolymarketNewsArbAgent: polymarket broker not active.")
            return []

        # Find the data source among databus providers
        ds = getattr(data, "_polymarket_source", None)
        if not ds:
            logger.debug("PolymarketNewsArbAgent: PolymarketDataSource not found in DataBus.")
            return []

        # Gather recent headlines
        headlines = await self._fetch_recent_headlines()
        if not headlines:
            logger.debug("PolymarketNewsArbAgent: No recent headlines found.")
            return []

        now = datetime.now(timezone.utc)
        opportunities = []
        scanned = 0

        # Scan tags
        for tag in self.tags:
            markets = await ds.get_markets(tag=tag, closed=False, limit=self.max_markets)
            for mkt in markets:
                if scanned >= self.max_markets:
                    break

                if mkt.volume_24h < self.min_volume:
                    continue

                if mkt.close_time:
                    try:
                        ct = datetime.fromisoformat(mkt.close_time.replace("Z", "+00:00"))
                        days_diff = (ct - now).days
                        if days_diff < self.min_days:
                            continue
                    except ValueError:
                        pass
                
                scanned += 1
                
                # Ask LLM
                prompt = self._build_prompt(mkt, headlines)
                response = await self.structured_call(
                    system_prompt="You are a quantitative prediction market analyst. Output valid JSON only.",
                    prompt=prompt,
                    schema={
                        "type": "object",
                        "properties": {
                            "implied_probability": {"type": "integer", "description": "Probability of YES from 0 to 100"},
                            "confidence": {"type": "integer", "description": "Confidence from 0 to 100"},
                            "reasoning": {"type": "string", "description": "Short explanation"}
                        },
                        "required": ["implied_probability", "confidence", "reasoning"]
                    }
                )

                if not response:
                    continue
                
                llm_prob = response.get("implied_probability", 50)
                confidence = response.get("confidence", 0)
                
                if confidence < self.min_confidence:
                    continue

                market_prob = mkt.yes_bid
                delta = abs(llm_prob - market_prob)

                if delta > self.threshold_cents:
                    logger.info("Polymarket News Arb Match: %s (LLM: %d, Mkt: %d, Conf: %d)", mkt.ticker, llm_prob, market_prob, confidence)
                    
                    # Target price is mid of gap
                    target_cents = market_prob + (self.threshold_cents if llm_prob > market_prob else -self.threshold_cents)
                    # Convert to 0-1 for polymarket
                    limit_price = round(target_cents / 100.0, 3)
                    
                    sym = mkt.as_symbol
                    order_side = OrderSide.BUY if llm_prob > market_prob else OrderSide.SELL # SELL = Buy NO in proxy
                    
                    opportunities.append(Opportunity(
                        id=f"poly_news_{mkt.ticker}_{now.timestamp()}",
                        agent_name=self.name,
                        symbol=sym,
                        signal=order_side.value,
                        confidence=confidence / 100.0,
                        reasoning=response.get("reasoning", ""),
                        broker_id="polymarket",
                        suggested_trade=LimitOrder(symbol=sym, side=order_side, quantity=10, account_id="POLY", limit_price=limit_price),
                        data={
                            "market_prob": market_prob,
                            "llm_prob": llm_prob,
                        },
                        timestamp=now
                    ))
        
        return opportunities

    async def _fetch_newsapi_headlines(self, query: str, page_size: int = 5) -> list[str]:
        """Fetch top headlines from NewsAPI for a given query."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={"q": query, "apiKey": self.newsapi_key, "pageSize": page_size},
                )
                resp.raise_for_status()
            articles = resp.json().get("articles", [])
            return [a["title"] for a in articles if a.get("title")]
        except Exception as exc:
            logger.warning("NewsAPI fetch failed for query '%s': %s", query, exc)
            return []

    async def _fetch_recent_headlines(self) -> list[str]:
        """Fetch headlines from NewsAPI if key is configured, otherwise fall back to RSS feeds."""
        if self.newsapi_key:
            return await self._fetch_newsapi_headlines("markets finance", page_size=15)

        # Fall back to RSS feeds
        import httpx
        import xml.etree.ElementTree as ET
        headlines = []
        async with httpx.AsyncClient() as client:
            for feed in self.rss_feeds:
                try:
                    resp = await client.get(feed, timeout=5.0)
                    resp.raise_for_status()
                    root = ET.fromstring(resp.text)
                    items = root.findall(".//item")
                    for item in items[:5]:
                        title = item.find("title")
                        if title is not None and title.text:
                            headlines.append(title.text)
                except Exception as e:
                    logger.debug("PolymarketNewsArbAgent failed to fetch RSS %s: %s", feed, e)
        return headlines

    def _build_prompt(self, mkt, headlines: list[str]) -> str:
        h_str = "\n- ".join(headlines)
        return f"""
Analyze the impact of recent news on this prediction market.

Market: {mkt.title} (Currently trading at {mkt.yes_bid}%)
Recent Headlines:
- {h_str}

Evaluate the true probability of this market resolving to YES given the headlines.
"""
