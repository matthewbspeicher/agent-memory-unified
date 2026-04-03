# data/bus.py
from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

from broker.models import (
    AccountBalance, Bar, OptionsChain, Position, Quote, Symbol,
)
from data.cache import TTLCache
from data.indicators import (
    BollingerBands, MACD,
    compute_bollinger, compute_ema, compute_macd, compute_rsi, compute_sma,
)
from data.sources.base import DataSource
from data.universe import get_universe

if TYPE_CHECKING:
    from broker.interfaces import Broker

logger = logging.getLogger(__name__)

# TTL constants (seconds)
QUOTE_TTL = 5
HISTORICAL_TTL = 300  # 5 minutes
UNIVERSE_TTL = 86400  # 24 hours


class DataBus:
    def __init__(
        self,
        sources: list[DataSource] | None = None,
        broker: Broker | None = None,
        trade_store=None,
        account_id: str = "",
        external_store=None,
        llm_client=None,
        kalshi_source=None,
        anthropic_key: str | None = None,
        news_source=None,
        polymarket_source=None,
        bittensor_source=None,
    ) -> None:
        self._sources = sources or []
        self._broker = broker
        self._trade_store = trade_store
        self._account_id = account_id
        self._external_store = external_store
        self._llm_client = llm_client
        self._kalshi_source = kalshi_source
        self._anthropic_key = anthropic_key
        self._news_source = news_source
        self._polymarket_source = polymarket_source
        self._bittensor_source = bittensor_source
        self._cache = TTLCache()
        self._quote_cache: dict[str, Quote] = {}  # streaming-sourced quotes (no TTL)

    # --- Market Data ---

    async def get_quote(self, symbol: Symbol) -> Quote:
        # Streaming cache takes priority (freshest data, no TTL)
        if symbol.ticker in self._quote_cache:
            return self._quote_cache[symbol.ticker]
        key = f"quote:{symbol.ticker}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        quote = await self._fetch_from_sources("get_quote", "supports_quotes", symbol)
        self._cache.set(key, quote, QUOTE_TTL)
        return quote

    async def update_quote_cache(self, symbol: Symbol, quote: Quote) -> None:
        """Update cached quote from streaming source. Resets TTL."""
        self._quote_cache[symbol.ticker] = quote

    def invalidate_quote_cache(self, symbols: list[str]) -> None:
        """Remove cached quotes, forcing next get_quote() to hit REST."""
        for s in symbols:
            self._quote_cache.pop(s, None)

    async def get_quotes(self, symbols: list[Symbol]) -> list[Quote]:
        return list(await asyncio.gather(*(self.get_quote(s) for s in symbols)))

    async def get_historical(
        self, symbol: Symbol, timeframe: str = "1d", period: str = "3mo",
    ) -> list[Bar]:
        key = f"hist:{symbol.ticker}:{timeframe}:{period}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        bars = await self._fetch_from_sources(
            "get_historical", "supports_historical", symbol, timeframe, period,
        )
        self._cache.set(key, bars, HISTORICAL_TTL)
        return bars

    async def get_options_chain(self, symbol: Symbol) -> OptionsChain:
        return await self._fetch_from_sources(
            "get_options_chain", "supports_options", symbol,
        )

    # --- Universe ---

    def get_universe(self, name: str | list[str]) -> list[Symbol]:
        key = f"universe:{name}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        symbols = get_universe(name)
        self._cache.set(key, symbols, UNIVERSE_TTL)
        return symbols

    # --- Technical Indicators ---

    async def get_rsi(self, symbol: Symbol, period: int = 14) -> float:
        bars = await self.get_historical(symbol, "1d", "3mo")
        return compute_rsi(bars, period)

    async def get_sma(self, symbol: Symbol, period: int = 20) -> float:
        bars = await self.get_historical(symbol, "1d", "3mo")
        return compute_sma(bars, period)

    async def get_ema(self, symbol: Symbol, period: int = 20) -> float:
        bars = await self.get_historical(symbol, "1d", "3mo")
        return compute_ema(bars, period)

    async def get_macd(self, symbol: Symbol) -> MACD:
        bars = await self.get_historical(symbol, "1d", "6mo")
        return compute_macd(bars)

    async def get_bollinger(
        self,
        symbol: Symbol,
        period: int = 20,
        num_std: float = 2.0,
    ) -> BollingerBands:
        bars = await self.get_historical(symbol, "1d", "3mo")
        return compute_bollinger(bars, period, num_std)

    # --- Portfolio (always from broker) ---

    async def get_positions(self) -> list[Position]:
        if not self._broker:
            return []
        return await self._broker.account.get_positions(self._account_id)

    async def get_all_positions(self, exclude_accounts: list[str] | None = None) -> list:
        ibkr = await self.get_positions()
        if self._external_store:
            external = await self._external_store.get_positions(exclude_accounts=exclude_accounts)
            return list(ibkr) + external
        return list(ibkr)

    async def get_balances(self) -> AccountBalance:
        if not self._broker:
            raise RuntimeError("No broker configured")
        return await self._broker.account.get_balances(self._account_id)

    async def get_sector(self, symbol: Symbol) -> str | None:
        if not self._broker:
            return None
        try:
            details = await self._broker.market_data.get_contract_details(symbol)
            return details.industry or None
        except Exception:
            return None

    async def get_recent_trades(self, limit: int = 100) -> list[dict]:
        if not self._trade_store:
            return []
        return await self._trade_store.get_trades(limit=limit)

    # --- Internal ---

    async def _fetch_from_sources(self, method: str, capability: str, *args):
        for source in self._sources:
            if not getattr(source, capability, False):
                continue
            try:
                return await getattr(source, method)(*args)
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning("Source %s failed for %s: %s", source.name, method, e)
                continue
        if self._broker:
            broker_market_data = getattr(self._broker, "market_data", None)
            if getattr(broker_market_data, "_data_bus", None) is self:
                raise RuntimeError(f"No source available for {method}")
            from data.sources.broker_source import BrokerSource
            fallback = BrokerSource(self._broker)
            return await getattr(fallback, method)(*args)
        raise RuntimeError(f"No source available for {method}")
