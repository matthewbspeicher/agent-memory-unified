"""
Polymarket Data Source for DataBus.

Provides PredictionContract polling and token ID caching.
"""

from __future__ import annotations

import logging
import time
import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Dict

from adapters.polymarket.client import PolymarketClient
from broker.models import PredictionContract, Quote, Symbol

logger = logging.getLogger(__name__)


@dataclass
class QuoteEntry:
    price: int
    last_updated: float = field(default_factory=time.time)


class ThreadSafeQuoteCache:
    """
    Sub-millisecond O(1) lookup cache for Polymarket quotes.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self):
        self._cache: Dict[str, QuoteEntry] = {}
        self._lock = asyncio.Lock()

    async def update(self, condition_id: str, price: int):
        async with self._lock:
            self._cache[condition_id] = QuoteEntry(
                price=price, last_updated=time.time()
            )

    async def get(self, condition_id: str, max_age: float = 2.0) -> Optional[int]:
        async with self._lock:
            entry = self._cache.get(condition_id)
            if not entry:
                return None
            if time.time() - entry.last_updated > max_age:
                return None
            return entry.price


class PolymarketDataSource:
    def __init__(self, client: PolymarketClient):
        self.client = client
        # condition_id -> (yes_token_id, no_token_id)
        self._token_id_cache: dict[str, tuple[str, str]] = {}
        # condition_id -> yes_cents (0-100), populated by PolymarketWebSocketFeed
        self._live_price_cache = ThreadSafeQuoteCache()

    async def get_live_quote(self, condition_id: str) -> Optional[int]:
        """
        Get the latest live quote from the cache.
        Returns None if the quote is missing or older than 2.0 seconds.
        """
        return await self._live_price_cache.get(condition_id, max_age=2.0)

    def _cache_tokens(self, market: dict) -> None:
        """Cache the YES and NO token IDs from a market response."""
        condition_id = market.get("condition_id")
        tokens = market.get("tokens", [])
        if condition_id and len(tokens) >= 2:
            # Polymarket tokens[0] is typically YES, tokens[1] is NO.
            # We can verify by looking at tokens[i]["outcome"]
            yes_id = None
            no_id = None
            for t in tokens:
                outcome = str(t.get("outcome", "")).upper()
                if outcome == "YES":
                    yes_id = t.get("token_id")
                elif outcome == "NO":
                    no_id = t.get("token_id")

            # Fallback to order if outcome string isn't clear
            if not yes_id and len(tokens) >= 1:
                yes_id = tokens[0].get("token_id")
            if not no_id and len(tokens) >= 2:
                no_id = tokens[1].get("token_id")

            if yes_id and no_id:
                self._token_id_cache[condition_id] = (yes_id, no_id)

    def resolve_token_id(self, condition_id: str, side: str = "YES") -> str | None:
        """Shared utility to map condition_id to token_id."""
        if condition_id not in self._token_id_cache:
            # Cache miss, fetch market to populate
            try:
                mkt = self.client.get_market(condition_id)
                self._cache_tokens(mkt)
            except Exception as e:
                logger.error(
                    "Polymarket: Failed to resolve token ID for %s: %s", condition_id, e
                )
                return None

        tokens = self._token_id_cache.get(condition_id)
        if not tokens:
            return None

        side = side.upper()
        return tokens[0] if side == "YES" else tokens[1]

    def _map_contract(self, mkt: dict) -> PredictionContract | None:
        try:
            tokens = mkt.get("tokens", [])
            if not tokens:
                return None

            self._cache_tokens(mkt)

            tags = mkt.get("tags", [])
            category = tags[0] if tags else "unknown"

            # price is mid/last from the tokens array (0-1). We convert to cents for PredictionContract.
            mkt.get("condition_id", "")
            # We skip the live cache here because _map_contract is sync and
            # the live cache is async. get_live_quote should be used for the latest data.
            yes_price_prob = Decimal(str(tokens[0].get("price", 0)))
            yes_cents = int(yes_price_prob * 100)

            closed = mkt.get("closed", False)
            active = mkt.get("active", True)

            # Figure out winner if resolved
            # winner token lookup
            result = None
            if closed and not active:
                for t in tokens:
                    if t.get("winner"):
                        result = str(t.get("outcome", "")).upper()
                        break

            return PredictionContract(
                ticker=mkt["condition_id"],
                title=mkt.get("question", mkt.get("title", "")),
                category=category,
                close_time=mkt.get("end_date_iso", ""),
                yes_bid=yes_cents,
                volume_24h=int(Decimal(str(mkt.get("volume_24hr", "0")))),
                result=result,
            )
        except Exception as e:
            logger.debug(
                "Polymarket: Skipping malformed market %s: %s",
                mkt.get("condition_id"),
                e,
            )
            return None

    async def get_markets(
        self,
        tag: str = None,
        closed: bool = False,
        next_cursor: str = "",
        limit: int = 100,
    ) -> list[PredictionContract]:
        """Fetch markets from Polymarket CLOB (non-blocking via asyncio.to_thread)."""
        import asyncio as _asyncio

        res = await _asyncio.to_thread(
            self.client.get_markets,
            tag=tag,
            active=not closed,
            next_cursor=next_cursor,
            limit=limit,
        )
        data = res.get("data", [])

        contracts = []
        for m in data:
            c = self._map_contract(m)
            if c:
                contracts.append(c)
        return contracts

    async def get_events(
        self,
        tags: list[str] | None = None,
        closed: bool = False,
        max_pages: int = 10,
    ) -> list[PredictionContract]:
        """Return current Gamma-API events as PredictionContracts.

        The CLOB `/markets` endpoint returns archived March-2023 data with
        `active=true, closed=true` mislabelling, so it's unusable for live
        matching. Gamma's `/events` is the current-event primitive.

        If `tags` is supplied, filter client-side (the upstream tag param
        has been unreliable in the past).
        """
        import asyncio as _asyncio

        raw = await _asyncio.to_thread(
            self.client.get_all_gamma_events,
            active=not closed,
            closed=closed,
            page_size=500,
            max_pages=max_pages,
        )
        allowed = {t.lower() for t in tags} if tags else None
        contracts: list[PredictionContract] = []
        for ev in raw:
            ev_tags = [t.get("label", "") if isinstance(t, dict) else str(t) for t in (ev.get("tags") or [])]
            if allowed is not None and not any(t.lower() in allowed for t in ev_tags):
                continue
            try:
                contracts.append(self._map_gamma_event(ev))
            except Exception as exc:
                logger.debug(
                    "PolymarketDataSource.get_events: skipping %s: %s",
                    ev.get("slug"),
                    exc,
                )
        return contracts

    def _map_gamma_event(self, ev: dict) -> PredictionContract:
        """Translate a Gamma event dict (camelCase) into a PredictionContract.

        Uses the first nested market for pricing. The event slug is the
        primary key — stable across Gamma and sufficient to identify the
        event without collapsing to per-outcome condition_ids.
        """
        markets = ev.get("markets") or []
        first = markets[0] if markets else {}

        # Gamma outcomePrices is a stringified JSON list of probabilities.
        yes_cents: int | None = None
        import json as _json

        op_raw = first.get("outcomePrices")
        if isinstance(op_raw, str):
            try:
                prices = _json.loads(op_raw)
                if prices:
                    yes_cents = int(Decimal(str(prices[0])) * 100)
            except Exception:
                pass
        elif isinstance(op_raw, list) and op_raw:
            try:
                yes_cents = int(Decimal(str(op_raw[0])) * 100)
            except Exception:
                pass

        ev_tags = ev.get("tags") or []
        first_tag = ""
        for t in ev_tags:
            if isinstance(t, dict):
                first_tag = t.get("label") or t.get("slug") or ""
            else:
                first_tag = str(t)
            if first_tag:
                break

        try:
            volume_24h = int(Decimal(str(ev.get("volume24hr") or first.get("volume24hr") or "0")))
        except Exception:
            volume_24h = 0

        # Use the first market's conditionId as the contract identifier
        # — that's what the CLOB orderbook + ws_feed key off, and what
        # SpreadTracker.match_index expects on the Polymarket side. The
        # event slug is preserved on title for matching purposes only.
        condition_id = (
            first.get("conditionId")
            or first.get("condition_id")
            or ev.get("slug")
            or str(ev.get("id", ""))
        )

        return PredictionContract(
            ticker=condition_id,
            title=ev.get("title", ""),
            category=first_tag,
            close_time=ev.get("endDate") or first.get("endDate") or "",
            yes_bid=yes_cents,
            volume_24h=volume_24h,
            result=None,
        )

    def get_market(self, condition_id: str) -> PredictionContract | None:
        """Fetch a single market by condition ID."""
        try:
            mkt = self.client.get_market(condition_id)
            return self._map_contract(mkt)
        except Exception as exc:
            logger.warning(
                "get_market failed for condition_id=%s: %s", condition_id, exc
            )
            return None

    def get_market_by_slug(self, slug: str) -> PredictionContract | None:
        """Fetch market by exact slug (for human queries)."""
        try:
            mkt = self.client.get_market_by_slug(slug)
            if mkt:
                return self._map_contract(mkt)
            return None
        except Exception as exc:
            logger.warning("get_market_by_slug failed for slug=%s: %s", slug, exc)
            return None

    async def search_markets(
        self, query: str, limit: int = 30
    ) -> list[PredictionContract]:
        """Search markets by title text (client-side filter on recent active markets)."""
        # Polymarket doesn't have a great full-text search endpoint on the CLOB.
        # We fetch active markets and client-side filter.
        contracts = await self.get_markets(limit=200)
        q = query.lower()
        matches = [
            c for c in contracts if q in c.ticker.lower() or q in c.title.lower()
        ]
        return matches[:limit]

    async def get_quote(self, symbol: Symbol) -> "Quote | None":
        """Fetch quote by condition_id (ticker)."""
        import asyncio

        mkt = await asyncio.to_thread(self.get_market, symbol.ticker)
        if not mkt:
            return None
        from broker.models import Quote
        from decimal import Decimal

        return Quote(
            symbol=symbol,
            bid=Decimal(str(mkt.yes_bid)) / Decimal("100")
            if mkt.yes_bid is not None
            else None,
            ask=Decimal(str(mkt.yes_ask)) / Decimal("100")
            if mkt.yes_ask is not None
            else None,
            last=Decimal(str(mkt.yes_last)) / Decimal("100")
            if mkt.yes_last is not None
            else None,
            volume=mkt.volume_24h,
        )
