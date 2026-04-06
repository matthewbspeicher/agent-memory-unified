from __future__ import annotations
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from broker.interfaces import MarketDataProvider
from broker.models import Bar, ContractDetails, OptionsChain, Quote, Symbol
from adapters.alpaca.client import AlpacaClient

logger = logging.getLogger(__name__)


_TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "30m": "30Min",
    "60m": "1Hour",
    "1h": "1Hour",
    "1d": "1Day",
}


def _quote_last(ask: Decimal | None, bid: Decimal | None) -> Decimal | None:
    if ask is not None and bid is not None:
        return (ask + bid) / Decimal("2")
    return ask or bid


class AlpacaMarketDataProvider(MarketDataProvider):
    def __init__(self, client: AlpacaClient) -> None:
        self._client = client

    async def get_quote(self, symbol: Symbol) -> Quote:
        raw = await self._client.get_quote(symbol.ticker)
        q = raw.get("quote", raw)
        ask = Decimal(str(q["ap"])) if q.get("ap") else None
        bid = Decimal(str(q["bp"])) if q.get("bp") else None
        return Quote(
            symbol=symbol,
            ask=ask,
            bid=bid,
            last=_quote_last(ask, bid),
            volume=0,
        )

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        tickers = [s.ticker for s in symbols]
        raw = await self._client.get_quotes(tickers)
        quotes = raw.get("quotes", raw)
        result = []
        for symbol in symbols:
            q = quotes.get(symbol.ticker, {})
            if isinstance(q, dict):
                q = q.get("quote", q)
            ask = Decimal(str(q.get("ap", 0))) if q.get("ap") else None
            bid = Decimal(str(q.get("bp", 0))) if q.get("bp") else None
            result.append(
                Quote(
                    symbol=symbol,
                    ask=ask,
                    bid=bid,
                    last=_quote_last(ask, bid),
                )
            )
        return result

    async def stream_quotes(
        self,
        symbols: list[Symbol],
        callback: Callable[[Quote], Any],
    ) -> None:
        raise NotImplementedError("Alpaca streaming deferred to Phase 2")

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str,
        period: str,
    ) -> list[Bar]:
        from datetime import timedelta

        # Convert period string to start/end dates
        now = datetime.now(timezone.utc)
        period_map = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
        days = period_map.get(period, 90)
        start = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
        end = now.strftime("%Y-%m-%dT23:59:59Z")

        alpaca_timeframe = _TIMEFRAME_MAP.get(timeframe, timeframe)
        raw_bars = await self._client.get_bars(
            symbol.ticker, alpaca_timeframe, start, end
        )
        return [
            Bar(
                symbol=symbol,
                open=Decimal(str(b["o"])),
                high=Decimal(str(b["h"])),
                low=Decimal(str(b["l"])),
                close=Decimal(str(b["c"])),
                volume=b.get("v", 0),
                timestamp=datetime.fromisoformat(b["t"].replace("Z", "+00:00")),
            )
            for b in raw_bars
        ]

    async def get_options_chain(
        self,
        symbol: Symbol,
        expiry: str | None = None,
    ) -> OptionsChain:
        raise NotImplementedError("Alpaca options deferred to Phase 2")

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        raw = await self._client.get_asset(symbol.ticker)
        return ContractDetails(
            symbol=symbol,
            long_name=raw.get("name", ""),
            min_tick=Decimal(str(raw.get("min_order_size", "0.01"))),
        )
