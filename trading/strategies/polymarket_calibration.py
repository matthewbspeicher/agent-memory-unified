"""
Polymarket Calibration Agent.

Cross-references Polymarket prices against Metaculus and Manifold APIs.
Emits an Opportunity if the gap exceeds threshold_cents.
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timezone

from agents.base import Agent
from agents.models import AgentConfig, Opportunity
from broker.models import LimitOrder, Symbol, OrderSide
from adapters.polymarket.data_source import PolymarketDataSource

logger = logging.getLogger(__name__)

class PolymarketCalibrationAgent(Agent):
    description = "Calibrates Polymarket prices against Metaculus and Manifold APIs."
    def __init__(self, config: AgentConfig, settings=None, **kwargs):
        super().__init__(config, **kwargs)

        params = config.parameters or {}
        self.metaculus_token: str | None = params.get("metaculus_token") or None
        # Fall back to global settings token if not provided in agent parameters
        if not self.metaculus_token and settings is not None:
            self.metaculus_token = getattr(settings, "metaculus_token", None) or None
        self.threshold = params.get("threshold_cents", 10)
        self.tags = params.get("tags", ["science", "technology", "economics"])
        self.min_similarity = params.get("min_match_similarity", 0.7)
        self.max_markets = params.get("max_markets_per_scan", 20)

    async def scan(self, data) -> list[Opportunity]:
        app_state = getattr(self.config, "_app_state", None)
        if app_state and "polymarket" not in app_state.brokers:
            return []

        ds = getattr(data, "_polymarket_source", None)
        if not ds:
            return []

        opportunities = []
        now = datetime.now(timezone.utc)
        scanned = 0

        for tag in self.tags:
            markets = await ds.get_markets(tag=tag, closed=False, limit=self.max_markets)
            for mkt in markets:
                if scanned >= self.max_markets:
                    break
                scanned += 1
                
                # We could run text matching locally, but since we rely on external 
                # APIs we issue queries based on the title. A simple implementation
                # takes the title text and gets external probabilities.
                result = await self._fetch_external_probability(mkt.title)
                if not result:
                    continue

                external_prob, similarity = result
                ext_prob_cents = int(external_prob * 100)
                poly_cents = mkt.yes_bid
                delta = abs(ext_prob_cents - poly_cents)

                if delta > self.threshold:
                    logger.info("Poly Calibration Match [%s]: ext=%d, poly=%d", mkt.ticker, ext_prob_cents, poly_cents)
                    sym = mkt.as_symbol
                    action = OrderSide.BUY if ext_prob_cents > poly_cents else OrderSide.SELL
                    
                    opportunities.append(Opportunity(
                        id=f"poly_calib_{mkt.ticker}_{now.timestamp()}",
                        agent_name=self.name,
                        symbol=sym,
                        signal="ARB",
                        confidence=round(similarity * min(delta / 30, 1.0), 3),
                        reasoning=f"Calibration Arb.\nQ:{mkt.title}",
                        broker_id="polymarket",
                        suggested_trade=LimitOrder(symbol=sym, side=action, quantity=10, account_id="POLY", limit_price=poly_cents / 100.0),
                        data={
                            "poly_prob": poly_cents,
                            "external_prob": ext_prob_cents
                        },
                        timestamp=now
                    ))
        
        return opportunities

    async def _fetch_external_probability(self, search_term: str) -> tuple[float, float] | None:
        """Fetch probability from Manifold or Metaculus (fallback)."""
        import difflib
        import httpx
        query = urllib.parse.quote(search_term)

        # --- Manifold first ---
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"https://manifold.markets/api/v0/search-markets?term={query}&limit=1",
                    timeout=5.0,
                )
                if res.status_code == 200:
                    data = res.json()
                    if data and len(data) > 0:
                        m = data[0]
                        ratio = difflib.SequenceMatcher(
                            None,
                            search_term.lower(),
                            m.get("question", m.get("title", "")).lower(),
                        ).ratio()
                        if ratio >= self.min_similarity and "probability" in m:
                            return (float(m["probability"]), ratio)
        except Exception as e:
            logger.warning("Manifold query failed: %s", e)

        # --- Metaculus fallback ---
        try:
            headers: dict = {}
            if self.metaculus_token:
                headers["Authorization"] = f"Bearer {self.metaculus_token}"
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    "https://www.metaculus.com/api2/questions/",
                    params={"search": search_term, "type": "forecast", "status": "open",
                            "forecast_type": "binary", "limit": 1},
                    headers=headers,
                    timeout=5.0,
                )
                if res.status_code == 200:
                    results = res.json().get("results", [])
                    if results:
                        q = results[0]
                        ratio = difflib.SequenceMatcher(
                            None,
                            search_term.lower(),
                            q.get("title", "").lower(),
                        ).ratio()
                        if ratio >= self.min_similarity:
                            community_prob = q.get("community_prediction")
                            if community_prob is not None:
                                return (float(community_prob), ratio)
        except Exception as e:
            logger.warning("Metaculus fallback query failed: %s", e)

        return None
