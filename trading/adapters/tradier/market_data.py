from __future__ import annotations
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from broker.interfaces import MarketDataProvider
from broker.models import (
    AssetType,
    Bar,
    ContractDetails,
    OptionRight,
    OptionsChain,
    Quote,
    Symbol,
)
from adapters.tradier.client import TradierClient

logger = logging.getLogger(__name__)

_INTRADAY_INTERVALS = {"1min", "5min", "15min"}
_INTRADAY_MAX_DAYS = 35


class TradierMarketDataProvider(MarketDataProvider):
    def __init__(self, client: TradierClient) -> None:
        self._client = client

    async def get_quote(self, symbol: Symbol) -> Quote:
        raw = await self._client.get_quote(symbol.ticker)
        q = raw.get("quotes", {}).get("quote", {})
        return Quote(
            symbol=symbol,
            last=Decimal(str(q["last"])) if q.get("last") else None,
            bid=Decimal(str(q["bid"])) if q.get("bid") else None,
            ask=Decimal(str(q["ask"])) if q.get("ask") else None,
            volume=q.get("volume", 0),
        )

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        tickers = [s.ticker for s in symbols]
        raw = await self._client.get_quotes(tickers)
        quotes_data = raw.get("quotes", {}).get("quote", [])
        if isinstance(quotes_data, dict):
            quotes_data = [quotes_data]

        result = []
        for q in quotes_data:
            sym = next((s for s in symbols if s.ticker == q.get("symbol")), symbols[0])
            result.append(
                Quote(
                    symbol=sym,
                    last=Decimal(str(q["last"])) if q.get("last") else None,
                    bid=Decimal(str(q["bid"])) if q.get("bid") else None,
                    ask=Decimal(str(q["ask"])) if q.get("ask") else None,
                    volume=q.get("volume", 0),
                )
            )
        return result

    async def stream_quotes(
        self,
        symbols: list[Symbol],
        callback: Callable[[Quote], Any],
    ) -> None:
        raise NotImplementedError("Tradier SSE streaming deferred to Phase 2")

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str,
        period: str,
    ) -> list[Bar]:
        now = datetime.now(timezone.utc)
        period_map = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
        days = period_map.get(period, 90)

        # Map timeframe to Tradier interval
        tf_map = {
            "1Min": "1min",
            "5Min": "5min",
            "15Min": "15min",
            "1D": "daily",
            "1d": "daily",
        }
        interval = tf_map.get(timeframe, "daily")

        # Warn about intraday data limitation
        if interval in _INTRADAY_INTERVALS and days > _INTRADAY_MAX_DAYS:
            logger.warning(
                "Tradier intraday data limited to ~%d days; requested %d days for %s %s. "
                "Returning what's available.",
                _INTRADAY_MAX_DAYS,
                days,
                symbol.ticker,
                interval,
            )

        start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        raw_bars = await self._client.get_historical(
            symbol.ticker, interval, start, end
        )
        return [
            Bar(
                symbol=symbol,
                open=Decimal(str(b.get("open", 0))),
                high=Decimal(str(b.get("high", 0))),
                low=Decimal(str(b.get("low", 0))),
                close=Decimal(str(b.get("close", 0))),
                volume=b.get("volume", 0),
                timestamp=datetime.strptime(b["date"], "%Y-%m-%d")
                if "date" in b
                else datetime.now(timezone.utc),
            )
            for b in raw_bars
        ]

    async def get_options_chain(
        self,
        symbol: Symbol,
        expiry: str | None = None,
    ) -> OptionsChain:
        if expiry is None:
            expirations = await self._client.get_options_expirations(symbol.ticker)
            if not expirations:
                return OptionsChain(symbol=symbol)
            expiry = expirations[0]

        raw = await self._client.get_options_chain(symbol.ticker, expiry)
        options = raw.get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]

        calls = []
        puts = []
        strikes = set()
        for opt in options:
            strike = Decimal(str(opt.get("strike", 0)))
            strikes.add(strike)
            exp_date = (
                date.fromisoformat(opt["expiration_date"])
                if opt.get("expiration_date")
                else None
            )
            right = (
                OptionRight.CALL
                if opt.get("option_type") == "call"
                else OptionRight.PUT
            )

            detail = ContractDetails(
                symbol=Symbol(
                    ticker=opt.get("symbol", ""),
                    asset_type=AssetType.OPTION,
                    expiry=exp_date,
                    strike=strike,
                    right=right,
                    multiplier=100,
                ),
                long_name=f"{symbol.ticker} {expiry} {strike} {'C' if right == OptionRight.CALL else 'P'}",
            )

            if right == OptionRight.CALL:
                calls.append(detail)
            else:
                puts.append(detail)

        return OptionsChain(
            symbol=symbol,
            expirations=[date.fromisoformat(expiry)] if expiry else [],
            strikes=sorted(strikes),
            calls=calls,
            puts=puts,
        )

    async def get_contract_details(self, symbol: Symbol) -> ContractDetails:
        return ContractDetails(symbol=symbol)
