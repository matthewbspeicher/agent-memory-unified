# data/bus.py
from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

from broker.models import (
    AccountBalance,
    Bar,
    OptionsChain,
    Position,
    Quote,
    Symbol,
)
from data.cache import TTLCache
from data.indicators import (
    BollingerBands,
    MACD,
    compute_atr,
    compute_bollinger,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_sma,
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

    async def get_order_book(self, symbol: Symbol, limit: int = 20) -> dict:
        return await self._fetch_from_sources(
            "get_order_book", "supports_order_book", symbol, limit
        )

    async def get_historical(
        self,
        symbol: Symbol,
        timeframe: str = "1d",
        period: str = "3mo",
    ) -> list[Bar]:
        key = f"hist:{symbol.ticker}:{timeframe}:{period}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        bars = await self._fetch_from_sources(
            "get_historical",
            "supports_historical",
            symbol,
            timeframe,
            period,
        )
        self._cache.set(key, bars, HISTORICAL_TTL)
        return bars

    async def get_options_chain(self, symbol: Symbol) -> OptionsChain:
        return await self._fetch_from_sources(
            "get_options_chain",
            "supports_options",
            symbol,
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

    # --- Summary Methods (context-window-friendly, inspired by tradingview-mcp) ---

    async def get_market_summary(self, symbol: Symbol) -> dict:
        """Single-call compact summary: quote + key indicators + volatility.
        Returns a dict instead of raw bar arrays — saves ~95% of tokens."""
        summary: dict = {"symbol": symbol.ticker}
        try:
            quote = await self.get_quote(symbol)
            summary["price"] = float(quote.last) if quote.last else None
            summary["bid"] = float(quote.bid) if quote.bid else None
            summary["ask"] = float(quote.ask) if quote.ask else None
        except Exception:
            summary["price"] = None

        try:
            summary["rsi_14"] = round(await self.get_rsi(symbol, 14), 2)
        except Exception:
            pass
        try:
            summary["ema_20"] = round(await self.get_ema(symbol, 20), 2)
            summary["ema_200"] = round(await self.get_ema(symbol, 200), 2)
        except Exception:
            pass
        try:
            macd = await self.get_macd(symbol)
            summary["macd_histogram"] = round(macd.histogram, 4)
        except Exception:
            pass
        try:
            bb = await self.get_bollinger(symbol)
            summary["bb_upper"] = round(bb.upper, 2)
            summary["bb_lower"] = round(bb.lower, 2)
            summary["bb_width"] = round(bb.upper - bb.lower, 2)
        except Exception:
            pass
        try:
            bars = await self.get_historical(symbol, "1d", "3mo")
            summary["atr_14"] = round(compute_atr(bars, 14), 4)
        except Exception:
            pass

        return summary

    async def get_key_levels(self, symbol: Symbol, timeframe: str = "1d") -> dict:
        """Support/resistance via recent high/low and pivot points."""
        bars = await self.get_historical(symbol, timeframe, "3mo")
        if not bars:
            return {}
        recent = bars[-20:] if len(bars) >= 20 else bars
        highs = [float(b.high) for b in recent]
        lows = [float(b.low) for b in recent]
        last = bars[-1]
        h, l, c = float(last.high), float(last.low), float(last.close)
        pivot = (h + l + c) / 3
        return {
            "symbol": symbol.ticker,
            "recent_high": max(highs),
            "recent_low": min(lows),
            "pivot": round(pivot, 4),
            "r1": round(2 * pivot - l, 4),
            "s1": round(2 * pivot - h, 4),
            "r2": round(pivot + (h - l), 4),
            "s2": round(pivot - (h - l), 4),
        }

    async def get_volatility_summary(self, symbol: Symbol) -> dict:
        """ATR, Bollinger width, and recent range vs average."""
        bars = await self.get_historical(symbol, "1d", "3mo")
        if not bars:
            return {}
        atr = compute_atr(bars, 14)
        bb = await self.get_bollinger(symbol)
        price = float(bars[-1].close)
        recent_ranges = [float(b.high) - float(b.low) for b in bars[-20:]]
        avg_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else 0

        return {
            "symbol": symbol.ticker,
            "atr_14": round(atr, 4),
            "atr_pct": round(atr / price * 100, 2) if price else 0,
            "bb_width": round(bb.upper - bb.lower, 2),
            "bb_width_pct": round((bb.upper - bb.lower) / bb.middle * 100, 2)
            if bb.middle
            else 0,
            "avg_daily_range": round(avg_range, 4),
            "last_range": round(recent_ranges[-1], 4) if recent_ranges else 0,
        }

    async def get_historical_summary(
        self,
        symbol: Symbol,
        timeframe: str = "1d",
        period: str = "3mo",
    ) -> dict:
        """Compact stats from historical bars instead of raw bar arrays.
        Use when you need context but not every single OHLCV bar."""
        bars = await self.get_historical(symbol, timeframe, period)
        if not bars:
            return {}
        closes = [float(b.close) for b in bars]
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]
        volumes = [float(b.volume) for b in bars]
        return {
            "symbol": symbol.ticker,
            "timeframe": timeframe,
            "period": period,
            "bar_count": len(bars),
            "open_first": float(bars[0].open),
            "close_last": float(bars[-1].close),
            "high": max(highs),
            "low": min(lows),
            "avg_close": round(sum(closes) / len(closes), 4),
            "avg_volume": round(sum(volumes) / len(volumes), 0),
            "change_pct": round((closes[-1] - closes[0]) / closes[0] * 100, 2)
            if closes[0]
            else 0,
            "trend": "up"
            if closes[-1] > closes[0]
            else "down"
            if closes[-1] < closes[0]
            else "flat",
        }

    # --- Portfolio (always from broker) ---

    async def get_positions(self) -> list[Position]:
        if not self._broker:
            return []
        return await self._broker.account.get_positions(self._account_id)

    async def get_all_positions(
        self, exclude_accounts: list[str] | None = None
    ) -> list:
        ibkr = await self.get_positions()
        if self._external_store:
            external = await self._external_store.get_positions(
                exclude_accounts=exclude_accounts
            )
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

    async def get_htf_trend(self, symbol: Symbol, htf: str = "4h") -> dict:
        """Get higher-timeframe trend direction.

        Note: "4h" is supported by BitGet and IBKR adapters.
        Falls back to "1d" if 4h unavailable.
        """
        try:
            bars = await self.get_historical(symbol, timeframe=htf, period="3mo")
        except Exception:
            bars = await self.get_historical(symbol, timeframe="1d", period="3mo")

        if not bars or len(bars) < 50:
            return {
                "symbol": str(symbol),
                "htf": htf,
                "trend": "neutral",
                "confidence": 0.0,
            }

        closes = [float(b.close) for b in bars]
        sma_20 = sum(closes[-20:]) / 20
        sma_50 = sum(closes[-50:]) / 50
        current = closes[-1]

        if sma_20 > sma_50 and current > sma_20:
            trend = "bullish"
        elif sma_20 < sma_50 and current < sma_20:
            trend = "bearish"
        else:
            trend = "neutral"

        separation = abs(sma_20 - sma_50) / sma_50
        confidence = min(1.0, separation * 10)

        return {
            "symbol": str(symbol),
            "htf": htf,
            "trend": trend,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "confidence": confidence,
        }

    async def check_htf_alignment(
        self, symbol: Symbol, side: str, htf: str = "4h"
    ) -> bool:
        """Check if trade direction aligns with HTF trend."""
        htf_data = await self.get_htf_trend(symbol, htf)

        if htf_data["confidence"] < 0.3:
            return True

        if side == "BUY" and htf_data["trend"] == "bullish":
            return True
        elif side == "SELL" and htf_data["trend"] == "bearish":
            return True
        elif htf_data["trend"] == "neutral":
            return True

        return False

    # --- Prediction Markets ---

    async def get_kalshi_markets(self, category: str | None = None) -> list:
        """Delegate to the Kalshi data source for prediction market data."""
        if not self._kalshi_source:
            return []
        return await self._kalshi_source.get_markets(category=category)

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

    async def close(self) -> None:
        """Close all underlying data sources and release resources."""
        import inspect

        for source in self._sources:
            if hasattr(source, "close"):
                try:
                    if inspect.iscoroutinefunction(source.close):
                        await source.close()
                    else:
                        source.close()
                except Exception as e:
                    logger.warning("Failed to close data source %s: %s", getattr(source, "name", "unknown"), e)

        if hasattr(self, "_massive_source") and self._massive_source:
            if hasattr(self._massive_source, "close"):
                try:
                    if inspect.iscoroutinefunction(self._massive_source.close):
                        await self._massive_source.close()
                    else:
                        self._massive_source.close()
                except Exception as e:
                    logger.warning("Failed to close massive source: %s", e)

        if hasattr(self, "_kalshi_source") and self._kalshi_source:
            if hasattr(self._kalshi_source, "close"):
                try:
                    if inspect.iscoroutinefunction(self._kalshi_source.close):
                        await self._kalshi_source.close()
                    else:
                        self._kalshi_source.close()
                except Exception as e:
                    logger.warning("Failed to close kalshi source: %s", e)
