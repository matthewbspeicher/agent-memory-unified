"""RegimeDetector — classifies market regime using ADX, volatility, and SMA slope."""

from __future__ import annotations
import logging
import math
from datetime import datetime, timezone
from typing import Any

from regime.models import (
    MarketRegime,
    RegimeSnapshot,
    LiquidityRegime,
    LiquiditySnapshot,
)

logger = logging.getLogger(__name__)

# Minimum bars required to make a regime determination
MIN_BARS = 20

# Thresholds
ADX_TRENDING_THRESHOLD = 25.0  # ADX > 25 indicates a trend
ADX_STRONG_TREND_THRESHOLD = 40.0  # ADX > 40 is a strong trend
HIGH_VOL_THRESHOLD = 0.30  # Annualized vol > 30%
LOW_VOL_THRESHOLD = 0.10  # Annualized vol < 10%


def _compute_true_range(bars: list) -> list[float]:
    """Compute True Range for each bar (excluding the first)."""
    tr_list = []
    for i in range(1, len(bars)):
        high = float(bars[i].high)
        low = float(bars[i].low)
        prev_close = float(bars[i - 1].close)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    return tr_list


def _compute_adx(bars: list, period: int = 14) -> float:
    """Simplified ADX computation."""
    if len(bars) < period + 2:
        return 0.0

    tr_list = _compute_true_range(bars)

    plus_dm = []
    minus_dm = []
    for i in range(1, len(bars)):
        up_move = float(bars[i].high) - float(bars[i - 1].high)
        down_move = float(bars[i - 1].low) - float(bars[i].low)
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    def smooth(values: list, n: int) -> list[float]:
        if len(values) < n:
            return []
        result = [sum(values[:n])]
        for v in values[n:]:
            result.append(result[-1] - result[-1] / n + v)
        return result

    atr = smooth(tr_list, period)
    plus_smooth = smooth(plus_dm, period)
    minus_smooth = smooth(minus_dm, period)

    if not atr or not plus_smooth or not minus_smooth:
        return 0.0

    # DX list
    dx_list = []
    for i in range(len(atr)):
        if atr[i] == 0:
            continue
        plus_di = 100 * plus_smooth[i] / atr[i]
        minus_di = 100 * minus_smooth[i] / atr[i]
        di_sum = plus_di + minus_di
        if di_sum == 0:
            continue
        dx = 100 * abs(plus_di - minus_di) / di_sum
        dx_list.append(dx)

    if not dx_list:
        return 0.0

    # ADX = smoothed DX
    adx_period = min(period, len(dx_list))
    adx = sum(dx_list[:adx_period]) / adx_period
    for dx in dx_list[adx_period:]:
        adx = (adx * (adx_period - 1) + dx) / adx_period

    return adx


def _compute_volatility(bars: list, period: int = 20) -> float:
    """Compute annualized volatility from daily returns."""
    if len(bars) < period + 1:
        return 0.0

    closes = [float(b.close) for b in bars[-(period + 1) :]]
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            ret = math.log(closes[i] / closes[i - 1])
            returns.append(ret)

    if len(returns) < 2:
        return 0.0

    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    daily_vol = math.sqrt(variance)
    annualized = daily_vol * math.sqrt(252)
    return annualized


def _compute_sma_slope(bars: list, period: int = 50) -> float:
    """
    Compute the slope of the SMA over the last `period` bars, normalized
    by the first SMA value. Returns a fraction (e.g., 0.02 = 2% upslope).
    """
    if len(bars) < period + 5:
        return 0.0

    def sma(window: list) -> float:
        return sum(float(b.close) for b in window) / len(window)

    # Compare SMA of last `period` bars vs SMA of period bars ago
    sma_now = sma(bars[-period:])
    sma_prev = sma(bars[-(period + 5) : -5])

    if sma_prev == 0:
        return 0.0

    return (sma_now - sma_prev) / sma_prev


class RegimeDetector:
    """
    Detects the current market regime using:
    - ADX (trend strength)
    - Annualized volatility
    - SMA slope (trend direction)

    Optionally enriches RegimeSnapshot with Alpha Vantage economic indicators
    (real GDP growth, Federal Funds Rate) when ``alpha_vantage_key`` is provided.
    """

    ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

    def __init__(
        self,
        adx_period: int = 14,
        vol_period: int = 20,
        sma_period: int = 50,
        alpha_vantage_key: str | None = None,
    ) -> None:
        self._adx_period = adx_period
        self._vol_period = vol_period
        self._sma_period = sma_period
        self._alpha_vantage_key = alpha_vantage_key

    def detect(self, bars: list) -> MarketRegime:
        """Return the detected MarketRegime for the given bars."""
        snapshot = self.detect_with_snapshot(bars)
        return snapshot.regime

    def detect_with_snapshot(self, bars: list) -> RegimeSnapshot:
        """Return a full RegimeSnapshot including supporting indicator values."""
        if not bars or len(bars) < MIN_BARS:
            return RegimeSnapshot(
                regime=MarketRegime.UNKNOWN,
                detected_at=datetime.now(timezone.utc),
                bars_analyzed=len(bars) if bars else 0,
            )

        adx = _compute_adx(bars, self._adx_period)
        volatility = _compute_volatility(bars, self._vol_period)
        sma_slope = _compute_sma_slope(bars, self._sma_period)

        regime = self._classify(adx, volatility, sma_slope)

        logger.debug(
            "Regime detected: %s (ADX=%.1f, vol=%.1f%%, slope=%.3f)",
            regime.value,
            adx,
            volatility,
            sma_slope,
        )

        return RegimeSnapshot(
            regime=regime,
            detected_at=datetime.now(timezone.utc),
            adx=round(adx, 2),
            volatility_pct=round(volatility * 100, 2),
            sma_slope=round(sma_slope, 4),
            bars_analyzed=len(bars),
        )

    async def detect_with_snapshot_enriched(self, bars: list) -> RegimeSnapshot:
        """
        Like ``detect_with_snapshot`` but additionally fetches Alpha Vantage
        economic indicators and stores them in ``RegimeSnapshot.economic_data``.

        Falls back gracefully — if the key is missing or the request fails,
        the snapshot is returned without economic data.
        """
        snapshot = self.detect_with_snapshot(bars)
        if self._alpha_vantage_key:
            snapshot.economic_data = await self._fetch_economic_indicators()
        return snapshot

    async def _fetch_economic_indicators(self) -> dict[str, Any]:
        """
        Fetch supplementary economic context from Alpha Vantage:
        - REAL_GDP (quarterly) — proxy for growth regime
        - FEDERAL_FUNDS_RATE (monthly) — interest rate environment

        Returns a dict with keys ``gdp`` and ``fed_rate``, each containing the
        most recent data point from the respective series, or ``None`` on failure.
        """
        import httpx

        key = self._alpha_vantage_key
        result: dict[str, Any] = {"gdp": None, "fed_rate": None}

        async def _fetch(function: str, interval: str) -> dict | None:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        self.ALPHA_VANTAGE_BASE,
                        params={
                            "function": function,
                            "interval": interval,
                            "apikey": key,
                        },
                    )
                    resp.raise_for_status()
                data = resp.json()
                # Alpha Vantage returns {"data": [{"date": "...", "value": "..."}, ...]}
                entries = data.get("data", [])
                if entries:
                    latest = entries[0]
                    return {
                        "date": latest.get("date"),
                        "value": latest.get("value"),
                    }
            except Exception as exc:
                logger.warning("Alpha Vantage fetch failed for %s: %s", function, exc)
            return None

        import asyncio

        gdp_task = asyncio.create_task(_fetch("REAL_GDP", "quarterly"))
        rate_task = asyncio.create_task(_fetch("FEDERAL_FUNDS_RATE", "monthly"))
        result["gdp"], result["fed_rate"] = await asyncio.gather(gdp_task, rate_task)
        return result

    def _classify(
        self, adx: float, volatility: float, sma_slope: float
    ) -> MarketRegime:
        """Apply classification rules."""
        # High volatility overrides trend detection
        if volatility > HIGH_VOL_THRESHOLD:
            return MarketRegime.HIGH_VOLATILITY

        # Trending regimes: ADX indicates trend strength
        if adx > ADX_TRENDING_THRESHOLD:
            if sma_slope > 0.005:  # 0.5% upslope
                return MarketRegime.TRENDING_UP
            elif sma_slope < -0.005:  # 0.5% downslope
                return MarketRegime.TRENDING_DOWN
            # Strong ADX but unclear direction
            return (
                MarketRegime.TRENDING_UP
                if sma_slope >= 0
                else MarketRegime.TRENDING_DOWN
            )

        # Low volatility regime
        if volatility < LOW_VOL_THRESHOLD:
            return MarketRegime.LOW_VOLATILITY

        # Default: sideways/range-bound
        return MarketRegime.SIDEWAYS


class LiquidityRegimeDetector:
    """
    Per-symbol liquidity regime detector for prediction markets.

    Classifies each symbol as FAVORABLE, UNFAVORABLE, or UNKNOWN based on
    bid-ask spread and 24h volume. Results are cached for `cache_ttl_seconds`
    to avoid hammering data sources on every agent tick.
    """

    def __init__(
        self,
        kalshi_source=None,
        poly_source=None,
        max_spread_cents: float = 5.0,
        min_volume: float = 1000,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """
        Args:
            kalshi_source: Data source with get_quote() and get_markets() for Kalshi.
            poly_source: Data source with get_quote() and get_markets() for Polymarket.
            max_spread_cents: Spread above this threshold → UNFAVORABLE.
            min_volume: Volume below this threshold → UNFAVORABLE.
            cache_ttl_seconds: How long to cache a symbol's snapshot (default 5 min).
        """
        self._kalshi = kalshi_source
        self._poly = poly_source
        self._max_spread = max_spread_cents
        self._min_volume = min_volume
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, LiquiditySnapshot] = {}  # symbol → snapshot

    def _resolve_source(self, symbol):
        """Return the appropriate data source for a symbol based on asset type or ticker."""
        # Polymarket tickers typically start with '0x' (on-chain contract addresses)
        if hasattr(symbol, "ticker") and symbol.ticker.startswith("0x"):
            return self._poly
        # Default to Kalshi for prediction markets
        return self._kalshi

    async def detect_symbol(self, symbol) -> LiquiditySnapshot:
        """
        Check liquidity for a specific symbol.

        Returns a cached snapshot if within TTL, otherwise fetches fresh data.
        Fails open: returns UNKNOWN if no source or quote is available.
        """
        cache_key = symbol.ticker
        cached = self._cache.get(cache_key)
        if (
            cached
            and (datetime.now(timezone.utc) - cached.detected_at).total_seconds()
            < self._cache_ttl
        ):
            return cached

        source = self._resolve_source(symbol)
        if not source:
            return LiquiditySnapshot(
                regime=LiquidityRegime.UNKNOWN,
                spread_cents=0.0,
                volume_24h=0.0,
                symbol=symbol.ticker,
                detected_at=datetime.now(timezone.utc),
            )

        try:
            quote = await source.get_quote(symbol)
        except Exception:
            quote = None

        if not quote:
            return LiquiditySnapshot(
                regime=LiquidityRegime.UNKNOWN,
                spread_cents=0.0,
                volume_24h=0.0,
                symbol=symbol.ticker,
                detected_at=datetime.now(timezone.utc),
            )

        spread = (float(quote.ask) - float(quote.bid)) * 100  # convert to cents
        volume = float(getattr(quote, "volume", 0) or 0)

        if spread > self._max_spread or volume < self._min_volume:
            regime = LiquidityRegime.UNFAVORABLE
        else:
            regime = LiquidityRegime.FAVORABLE

        snapshot = LiquiditySnapshot(
            regime=regime,
            spread_cents=round(spread, 4),
            volume_24h=volume,
            symbol=symbol.ticker,
            detected_at=datetime.now(timezone.utc),
        )
        self._cache[cache_key] = snapshot

        logger.debug(
            "LiquidityRegime for %s: %s (spread=%.2f¢, vol=%.0f)",
            symbol.ticker,
            regime.value,
            spread,
            volume,
        )
        return snapshot

    async def detect_platform(self, broker_id: str) -> LiquiditySnapshot:
        """
        Platform-level average liquidity for API overview.

        Fetches the top 20 markets and averages spread and volume.
        NOT used for per-symbol filtering — only for the /regime endpoint summary.
        """
        source = self._kalshi if broker_id == "kalshi" else self._poly
        if not source:
            return LiquiditySnapshot(
                regime=LiquidityRegime.UNKNOWN,
                spread_cents=0.0,
                volume_24h=0.0,
                symbol=broker_id,
                detected_at=datetime.now(timezone.utc),
            )

        try:
            markets = await source.get_markets(limit=20)
        except Exception:
            markets = []

        if not markets:
            return LiquiditySnapshot(
                regime=LiquidityRegime.UNKNOWN,
                spread_cents=0.0,
                volume_24h=0.0,
                symbol=broker_id,
                detected_at=datetime.now(timezone.utc),
            )

        spreads = []
        volumes = []
        for market in markets:
            try:
                bid = float(getattr(market, "bid", 0) or 0)
                ask = float(getattr(market, "ask", 0) or 0)
                if ask > bid >= 0:
                    spreads.append((ask - bid) * 100)
                vol = float(getattr(market, "volume_24h", 0) or 0)
                volumes.append(vol)
            except Exception:
                continue

        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        avg_volume = sum(volumes) / len(volumes) if volumes else 0.0

        if avg_spread > self._max_spread or avg_volume < self._min_volume:
            regime = LiquidityRegime.UNFAVORABLE
        else:
            regime = LiquidityRegime.FAVORABLE

        return LiquiditySnapshot(
            regime=regime,
            spread_cents=round(avg_spread, 4),
            volume_24h=round(avg_volume, 2),
            symbol=broker_id,
            detected_at=datetime.now(timezone.utc),
        )
