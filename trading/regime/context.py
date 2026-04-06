"""RegimeContextResolver — normalizes MarketRegime outputs into a stable vocabulary.

The resolved RegimeContext is cached for 60 seconds to avoid redundant SPY bar
fetches under load. SPY is used as the equity regime proxy for all equity strategies.
For prediction-market symbols, equity dimensions are set to "n/a" and the
LiquidityRegime is used for liquidity_regime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from regime.models import LiquidityRegime, MarketRegime

logger = logging.getLogger(__name__)

SOURCE_VERSION = "v1"
CACHE_TTL_SECONDS = 60


# ---------------------------------------------------------------------------
# Normalized vocabulary
# ---------------------------------------------------------------------------

_TREND_MAP: dict[MarketRegime, str] = {
    MarketRegime.TRENDING_UP: "uptrend",
    MarketRegime.TRENDING_DOWN: "downtrend",
    MarketRegime.SIDEWAYS: "range",
    MarketRegime.HIGH_VOLATILITY: "range",  # high-vol without clear direction → range
    MarketRegime.LOW_VOLATILITY: "range",  # low-vol without clear direction → range
    MarketRegime.UNKNOWN: "unknown",
}

_VOL_MAP: dict[MarketRegime, str] = {
    MarketRegime.HIGH_VOLATILITY: "high",
    MarketRegime.LOW_VOLATILITY: "low",
    MarketRegime.TRENDING_UP: "medium",
    MarketRegime.TRENDING_DOWN: "medium",
    MarketRegime.SIDEWAYS: "medium",
    MarketRegime.UNKNOWN: "unknown",
}

_LIQUIDITY_FROM_LIQUIDITY_REGIME: dict[LiquidityRegime, str] = {
    LiquidityRegime.FAVORABLE: "high",
    LiquidityRegime.UNFAVORABLE: "low",
    LiquidityRegime.UNKNOWN: "medium",
}


# ---------------------------------------------------------------------------
# RegimeContext dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeContext:
    """Normalized, stable regime snapshot for use across routing and analytics.

    Fields:
        trend_regime: "uptrend" | "downtrend" | "range" | "unknown"
        volatility_regime: "low" | "medium" | "high" | "unknown"
        liquidity_regime: "low" | "medium" | "high" | "unknown"
        event_regime: "normal" | "elevated"
        market_state: composite label e.g. "uptrend_high_vol_high_liq"
        source_version: resolver version for forward-compat
        as_of: UTC timestamp when this context was produced
    """

    trend_regime: str
    volatility_regime: str
    liquidity_regime: str
    event_regime: str
    market_state: str
    source_version: str
    as_of: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "trend_regime": self.trend_regime,
            "volatility_regime": self.volatility_regime,
            "liquidity_regime": self.liquidity_regime,
            "event_regime": self.event_regime,
            "market_state": self.market_state,
            "source_version": self.source_version,
            "as_of": self.as_of.isoformat(),
        }


def _build_market_state(trend: str, vol: str, liq: str) -> str:
    return f"{trend}_{vol}_vol_{liq}_liq"


def _normalize_equity(
    regime: MarketRegime, liquidity_regime: str = "medium"
) -> RegimeContext:
    """Map an equity MarketRegime to normalized RegimeContext."""
    trend = _TREND_MAP.get(regime, "unknown")
    vol = _VOL_MAP.get(regime, "unknown")
    return RegimeContext(
        trend_regime=trend,
        volatility_regime=vol,
        liquidity_regime=liquidity_regime,
        event_regime="normal",
        market_state=_build_market_state(trend, vol, liquidity_regime),
        source_version=SOURCE_VERSION,
        as_of=datetime.now(timezone.utc),
    )


def _build_prediction_market_context(liq_regime: LiquidityRegime) -> RegimeContext:
    """Build a prediction-market RegimeContext from a LiquidityRegime."""
    liq = _LIQUIDITY_FROM_LIQUIDITY_REGIME.get(liq_regime, "medium")
    return RegimeContext(
        trend_regime="n/a",
        volatility_regime="n/a",
        liquidity_regime=liq,
        event_regime="normal",
        market_state=f"prediction_market_{liq}_liq",
        source_version=SOURCE_VERSION,
        as_of=datetime.now(timezone.utc),
    )


def _unknown_context() -> RegimeContext:
    return RegimeContext(
        trend_regime="unknown",
        volatility_regime="unknown",
        liquidity_regime="unknown",
        event_regime="normal",
        market_state="unknown",
        source_version=SOURCE_VERSION,
        as_of=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# RegimeContextResolver
# ---------------------------------------------------------------------------


class RegimeContextResolver:
    """Wraps RegimeDetector and normalizes its output into RegimeContext.

    Results are cached for CACHE_TTL_SECONDS (default 60s) to prevent
    redundant SPY bar fetches when many opportunities route in rapid succession.
    """

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[RegimeContext, datetime]] = {}

    def resolve_from_regime(
        self, regime: MarketRegime, cache_key: str = "equity"
    ) -> RegimeContext:
        """Normalize an already-detected MarketRegime into RegimeContext.

        Useful when the caller has already fetched bars and detected the regime.
        Result is cached under ``cache_key`` for the configured TTL.
        """
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        ctx = _normalize_equity(regime)
        self._put_cache(cache_key, ctx)
        return ctx

    def resolve_from_snapshot(
        self, snapshot, cache_key: str = "equity"
    ) -> RegimeContext:
        """Normalize a RegimeSnapshot into RegimeContext."""
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if snapshot is None:
            ctx = _unknown_context()
        else:
            ctx = _normalize_equity(snapshot.regime)

        self._put_cache(cache_key, ctx)
        return ctx

    def resolve_from_liquidity(
        self, liq_regime: LiquidityRegime, symbol_ticker: str
    ) -> RegimeContext:
        """Normalize a LiquidityRegime for a prediction-market symbol."""
        cache_key = f"prediction:{symbol_ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        ctx = _build_prediction_market_context(liq_regime)
        self._put_cache(cache_key, ctx)
        return ctx

    def resolve_unknown(self) -> RegimeContext:
        """Return an unknown RegimeContext (no detection possible)."""
        return _unknown_context()

    def invalidate(self, cache_key: str = "equity") -> None:
        """Remove a cached entry."""
        self._cache.pop(cache_key, None)

    # ------------------------------------------------------------------
    # Internal cache helpers
    # ------------------------------------------------------------------

    def _get_cached(self, key: str) -> RegimeContext | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ctx, ts = entry
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if self._ttl > 0 and age <= self._ttl:
            return ctx
        del self._cache[key]
        return None

    def _put_cache(self, key: str, ctx: RegimeContext) -> None:
        self._cache[key] = (ctx, datetime.now(timezone.utc))
