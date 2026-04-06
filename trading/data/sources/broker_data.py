from __future__ import annotations
import asyncio
from decimal import Decimal
import logging

import yfinance as yf

from broker.models import Bar, Symbol, AssetType
from data.sources.base import DataSource

logger = logging.getLogger(__name__)

class BrokerHistoricalSource(DataSource):
    """
    Source for fetching historical data for traditional brokers like Fidelity and IBKR.
    Currently uses yfinance as the underlying provider for historical bars.
    """
    name = "broker_historical"
    supports_quotes = True
    supports_historical = True
    supports_options = False
    supports_fundamentals = False

    async def get_historical(
        self, symbol: Symbol, timeframe: str = "1d", period: str = "1mo",
    ) -> list[Bar]:
        """
        Fetches historical bars for a symbol.
        Handles Fidelity and IBKR specific symbol formats if necessary.
        """
        def _fetch():
            ticker = self._format_ticker(symbol)
            logger.info(f"Fetching historical data for {ticker} (original: {symbol.ticker})")
            
            try:
                df = yf.download(
                    ticker, period=period, interval=timeframe, progress=False,
                )
            except Exception as e:
                logger.error(f"Failed to download data for {ticker}: {e}")
                return []

            if df.empty:
                logger.warning(f"No historical data found for {ticker}")
                return []

            # yfinance >=0.2.31 returns multi-level columns if multiple tickers or other conditions
            if isinstance(df.columns, __import__('pandas').MultiIndex):
                # Try to drop the ticker level if it exists
                if ticker in df.columns.levels[1]:
                    df = df.xs(ticker, axis=1, level=1)
                else:
                    df = df.droplevel(1, axis=1)

            bars: list[Bar] = []
            for ts, row in df.iterrows():
                try:
                    bars.append(Bar(
                        symbol=symbol,
                        timestamp=ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts,
                        open=Decimal(str(float(row["Open"]))),
                        high=Decimal(str(float(row["High"]))),
                        low=Decimal(str(float(row["Low"]))),
                        close=Decimal(str(float(row["Close"]))),
                        volume=int(row["Volume"]),
                    ))
                except (KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed row for {ticker} at {ts}: {e}")
                    continue
            
            return bars

        return await asyncio.to_thread(_fetch)

    def _format_ticker(self, symbol: Symbol) -> str:
        """
        Formats the ticker for yfinance compatibility.
        Fidelity/IBKR often have different conventions for indices or multi-class stocks.
        """
        ticker = symbol.ticker
        
        # Example: IBKR uses 'BRK B', yfinance uses 'BRK-B'
        if " " in ticker:
            ticker = ticker.replace(" ", "-")
            
        # Example: Handle indices (e.g., SPX -> ^SPX)
        if symbol.asset_type == AssetType.STOCK and ticker in ["SPX", "NDX", "RUT"]:
            ticker = f"^{ticker}"
            
        return ticker

    async def get_quote(self, symbol: Symbol) -> Quote:
        raise NotImplementedError("Use YahooFinanceSource or BrokerSource for live quotes")

    async def get_options_chain(self, symbol: Symbol) -> OptionsChain:
        raise NotImplementedError("Options historical data ingestion not yet implemented")
