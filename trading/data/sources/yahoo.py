from __future__ import annotations
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any

import yfinance as yf

from broker.models import Bar, OptionsChain, Quote, Symbol
from data.sources.base import DataSource


class YahooFinanceSource(DataSource):
    name = "yahoo"
    supports_quotes = True
    supports_historical = True
    supports_options = False
    supports_fundamentals = False

    def _format_ticker(self, symbol: Symbol) -> str:
        ticker = symbol.ticker
        if symbol.asset_type.value == "CRYPTO" or ("USD" in ticker and len(ticker) > 3):
            if ticker.endswith("USD") and "-" not in ticker:
                ticker = ticker[:-3] + "-USD"
        if " " in ticker:
            ticker = ticker.replace(" ", "-")
        if symbol.asset_type.value == "STOCK" and ticker in ["SPX", "NDX", "RUT"]:
            ticker = f"^{ticker}"
        return ticker

    _YAHOO_UNSUPPORTED_TYPES = {"PREDICTION", "prediction"}

    async def get_quote(self, symbol: Symbol) -> Quote:
        if symbol.asset_type.value in self._YAHOO_UNSUPPORTED_TYPES:
            return Quote(
                symbol=symbol, bid=Decimal(0), ask=Decimal(0),
                last=Decimal(0), volume=0, timestamp=datetime.utcnow(),
            )

        def _fetch():
            ticker = self._format_ticker(symbol)
            t = yf.Ticker(ticker)
            info = t.fast_info
            return Quote(
                symbol=symbol,
                bid=Decimal(str(getattr(info, "bid", 0) or 0)),
                ask=Decimal(str(getattr(info, "ask", 0) or 0)),
                last=Decimal(str(getattr(info, "last_price", 0) or 0)),
                volume=int(getattr(info, "last_volume", 0) or 0),
                timestamp=datetime.utcnow(),
            )

        return await asyncio.to_thread(_fetch)

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str = "1d",
        period: str = "3mo",
    ) -> list[Bar]:
        if symbol.asset_type.value in self._YAHOO_UNSUPPORTED_TYPES:
            return []

        def _fetch():
            def _as_scalar(value: Any) -> Any:
                if hasattr(value, "iloc"):
                    return value.iloc[0]
                return value

            ticker = self._format_ticker(symbol)
            df = yf.download(
                ticker,
                period=period,
                interval=timeframe,
                progress=False,
            )
            if df.empty:
                return []
            if getattr(df.columns, "nlevels", 1) > 1:
                try:
                    tickers = df.columns.get_level_values(-1)
                    if ticker in tickers:
                        df = df.xs(ticker, axis=1, level=-1, drop_level=True)
                    else:
                        df = df.droplevel(-1, axis=1)
                except Exception:
                    df = df.droplevel(-1, axis=1)
            bars: list[Bar] = []
            for ts, row in df.iterrows():
                bars.append(
                    Bar(
                        symbol=symbol,
                        timestamp=ts.to_pydatetime(),
                        open=Decimal(str(float(_as_scalar(row["Open"])))),
                        high=Decimal(str(float(_as_scalar(row["High"])))),
                        low=Decimal(str(float(_as_scalar(row["Low"])))),
                        close=Decimal(str(float(_as_scalar(row["Close"])))),
                        volume=int(_as_scalar(row["Volume"])),
                    )
                )
            return bars

        return await asyncio.to_thread(_fetch)

    async def get_options_chain(self, symbol: Symbol) -> OptionsChain:
        raise NotImplementedError("Use broker source for options data")
