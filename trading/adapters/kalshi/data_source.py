"""
KalshiDataSource — DataBus source that surfaces Kalshi market data.

Registered alongside YahooFinanceSource and BrokerSource. Agents can call:
  data_bus.get_kalshi_markets(category="economics")
  data_bus.get_kalshi_quote(ticker)

The source wraps KalshiClient and translates raw API dicts into
PredictionContract + Quote objects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from broker.models import AssetType, PredictionContract, Quote, Symbol
from adapters.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


class KalshiDataSource:
    """
    Plugs into DataBus as a specialised source for prediction market data.
    Unlike stock DataSources it is NOT registered in the generic source list —
    it is accessed via two dedicated DataBus methods added by the wiring code.
    """

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # DataSource-compatible interface (used if wired into generic sources)
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: Symbol) -> Quote | None:
        if symbol.asset_type != AssetType.PREDICTION:
            return None
        try:
            ob = await self._client.get_orderbook(symbol.ticker, depth=5)
            from decimal import Decimal

            bid = None
            ask = None

            fp = ob.get("orderbook_fp", {})
            if "yes_dollars" in fp or "no_dollars" in fp:
                yes_bids = fp.get("yes_dollars", [])
                no_bids = fp.get("no_dollars", [])

                if yes_bids:
                    bid = Decimal(str(yes_bids[0][0]))
                if no_bids:
                    ask = Decimal("1.00") - Decimal(str(no_bids[0][0]))
            else:
                yes_bids = ob.get("yes", [])
                no_bids = ob.get("no", [])

                if yes_bids:
                    bid = Decimal(str(yes_bids[0][0])) / Decimal("100")
                if no_bids:
                    ask = (Decimal("100") - Decimal(str(no_bids[0][0]))) / Decimal(
                        "100"
                    )

            last = None
            try:
                trades = await self._client.get_trades(symbol.ticker, limit=1)
                if trades:
                    raw_price = trades[0].get("yes_price")
                    if raw_price is not None:
                        # old format was cents, new format might be dollars if string.
                        # guess based on value > 1? Usually Kalshi price is < 1 dollar.
                        # if it's > 1, it's cents.
                        pr = Decimal(str(raw_price))
                        last = pr / Decimal("100") if pr >= 1 else pr
            except Exception:
                pass  # it's fine if trades endpoint 404s for new markets

            return Quote(symbol=symbol, bid=bid, ask=ask, last=last)
        except Exception as exc:
            logger.warning(
                "KalshiDataSource.get_quote(%s) failed: %s", symbol.ticker, exc
            )
            return None

    # ------------------------------------------------------------------
    # Prediction-market-specific helpers (called by Kalshi agents)
    # ------------------------------------------------------------------

    async def get_markets(
        self,
        category: str | None = None,
        status: str = "open",
        max_pages: int = 5,
    ) -> list[PredictionContract]:
        """Return open Kalshi markets as typed PredictionContract objects."""
        raw = await self._client.get_all_markets(
            category=category, status=status, max_pages=max_pages
        )
        contracts: list[PredictionContract] = []
        for m in raw:
            try:
                contracts.append(self._parse_market(m))
            except Exception as exc:
                logger.debug("Skipping malformed market %s: %s", m.get("ticker"), exc)
        return contracts

    async def get_market(self, ticker: str) -> PredictionContract | None:
        """Fetch a single market by ticker."""
        try:
            raw = await self._client.get_market(ticker)
            return self._parse_market(raw)
        except Exception as exc:
            logger.warning("KalshiDataSource.get_market(%s) failed: %s", ticker, exc)
            return None

    def _parse_market(self, m: dict) -> PredictionContract:
        """Translate a raw Kalshi market dict to a PredictionContract."""
        close_ts = m.get("close_time") or m.get("expected_expiration_time") or ""
        try:
            close_time = datetime.fromisoformat(close_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            close_time = datetime.now(timezone.utc)

        return PredictionContract(
            ticker=m["ticker"],
            title=m.get("title", ""),
            category=m.get("category", ""),
            close_time=close_time,
            yes_bid=m.get("yes_bid"),
            yes_ask=m.get("yes_ask"),
            yes_last=m.get("last_price"),
            open_interest=m.get("open_interest", 0),
            volume_24h=m.get("volume_24h", 0),
            result=m.get("result"),
        )
