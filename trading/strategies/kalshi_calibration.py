"""
KalshiCalibrationAgent — cross-platform arbitrage against Metaculus forecasts.

Scan flow:
1. Fetch Metaculus questions (filtered by keyword/category)
2. Fuzzy-match to open Kalshi markets by title similarity
3. Compare Metaculus community prediction to Kalshi price
4. Emit Opportunity when gap > threshold_cents

agents.yaml example:
  - name: kalshi_calibration
    strategy: kalshi_calibration
    schedule: cron
    cron: "0 */6 * * *"
    action_level: suggest_trade
    parameters:
      threshold_cents: 10
      min_volume: 100
      max_markets: 50
      metaculus_token: ""   # optional — increases rate limits
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx

from agents.base import StructuredAgent
from agents.models import Opportunity, OpportunityStatus
from broker.models import LimitOrder, OrderSide, TIF

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)

METACULUS_API = "https://www.metaculus.com/api2"


def _title_similarity(a: str, b: str) -> float:
    """Very lightweight token-overlap similarity (no external deps needed)."""
    stop = {"will", "the", "a", "an", "in", "of", "by", "be", "is", "or", "to", "and"}
    tokens_a = {w.lower() for w in a.split() if len(w) > 2 and w.lower() not in stop}
    tokens_b = {w.lower() for w in b.split() if len(w) > 2 and w.lower() not in stop}
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


async def _fetch_metaculus_questions(
    search: str | None = None,
    token: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch open binary questions from Metaculus."""
    params: dict = {
        "type": "forecast",
        "status": "open",
        "forecast_type": "binary",
        "limit": limit,
        "order_by": "-activity",
    }
    if search:
        params["search"] = search
    headers = {}
    if token:
        headers["Authorization"] = f"Token {token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{METACULUS_API}/questions/", params=params, headers=headers)
            resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as exc:
        logger.warning("Metaculus fetch failed: %s", exc)
        return []


class KalshiCalibrationAgent(StructuredAgent):
    description = (
        "Compares Kalshi market prices to Metaculus community forecasts. "
        "Emits opportunities when the two platforms disagree by more than "
        "threshold_cents, betting on the Metaculus consensus."
    )

    async def scan(self, data: DataBus) -> list[Opportunity]:
        params = self.parameters
        threshold: int = int(params.get("threshold_cents", 10))
        min_volume: int = int(params.get("min_volume", 100))
        max_markets: int = int(params.get("max_markets", 50))
        metaculus_token: str | None = params.get("metaculus_token") or None
        # Fall back to global settings token if not provided in agent parameters
        if not metaculus_token:
            _settings = getattr(data, "_settings", None)
            if _settings is not None:
                metaculus_token = getattr(_settings, "metaculus_token", None) or None

        kalshi_source = getattr(data, "_kalshi_source", None)
        if kalshi_source is None:
            logger.warning("%s: no KalshiDataSource on DataBus — skipping", self.name)
            return []

        # Fetch data in parallel
        import asyncio
        kalshi_task = asyncio.create_task(
            kalshi_source.get_markets(status="open")
        )
        metaculus_task = asyncio.create_task(
            _fetch_metaculus_questions(token=metaculus_token, limit=200)
        )
        kalshi_markets, metaculus_qs = await asyncio.gather(kalshi_task, metaculus_task)

        # Filter liquid Kalshi markets
        liquid = [m for m in kalshi_markets if m.volume_24h >= min_volume and m.mid_probability is not None]
        liquid.sort(key=lambda m: m.volume_24h, reverse=True)
        liquid = liquid[:max_markets]

        opportunities: list[Opportunity] = []
        for contract in liquid:
            market_prob = contract.mid_probability
            if market_prob is None:
                continue

            # Find the best-matching Metaculus question
            best_q: dict | None = None
            best_sim = 0.0
            for q in metaculus_qs:
                sim = _title_similarity(contract.title, q.get("title", ""))
                if sim > best_sim:
                    best_sim = sim
                    best_q = q

            if best_q is None or best_sim < 0.25:
                continue  # no good match found

            # Metaculus community_prediction is 0–1
            community_prob: float | None = best_q.get("community_prediction")
            if community_prob is None:
                continue

            gap_cents = abs(round((community_prob - float(market_prob)) * 100))
            if gap_cents < threshold:
                continue

            direction = "YES" if community_prob > float(market_prob) else "NO"
            side = OrderSide.BUY if direction == "YES" else OrderSide.SELL
            limit_price = Decimal(str(round(market_prob, 2)))
            adjustment = Decimal("0.01") * (1 if direction == "YES" else -1)
            limit_price = max(Decimal("0.01"), min(Decimal("0.99"), limit_price + adjustment))

            symbol = contract.as_symbol
            suggested = LimitOrder(
                symbol=symbol,
                side=side,
                quantity=Decimal("10"),
                account_id="KALSHI",
                limit_price=limit_price,
                time_in_force=TIF.GTC,
            )

            # Confidence based on similarity match quality and gap size
            confidence = round(best_sim * min(gap_cents / 30, 1.0), 3)

            opportunities.append(Opportunity(
                id=str(uuid.uuid4()),
                agent_name=self.name,
                symbol=symbol,
                signal=direction,
                confidence=confidence,
                reasoning=(
                    f"Kalshi: {market_prob:.0%} | Metaculus: {community_prob:.0%} | "
                    f"Gap: {gap_cents}¢ | Match score: {best_sim:.2f}\n"
                    f"Kalshi: {contract.title}\n"
                    f"Metaculus: {best_q.get('title', '')}"
                ),
                data={
                    "kalshi_ticker": contract.ticker,
                    "kalshi_prob": float(market_prob),
                    "metaculus_prob": community_prob,
                    "metaculus_id": best_q.get("id"),
                    "match_similarity": round(best_sim, 3),
                    "gap_cents": gap_cents,
                    "volume_24h": contract.volume_24h,
                },
                timestamp=datetime.now(timezone.utc),
                suggested_trade=suggested,
                status=OpportunityStatus.PENDING,
            ))

        opportunities.sort(key=lambda o: o.confidence, reverse=True)
        return opportunities
