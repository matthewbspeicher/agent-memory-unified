"""Tests for regime/context.py — normalization, caching, null-safety."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from regime.context import (
    CACHE_TTL_SECONDS,
    RegimeContext,
    RegimeContextResolver,
    _normalize_equity,
    _unknown_context,
)
from regime.models import LiquidityRegime, MarketRegime


# ---------------------------------------------------------------------------
# RegimeContext dataclass
# ---------------------------------------------------------------------------


def test_regime_context_is_frozen():
    ctx = RegimeContext(
        trend_regime="uptrend",
        volatility_regime="medium",
        liquidity_regime="high",
        event_regime="normal",
        market_state="uptrend_medium_vol_high_liq",
        source_version="v1",
        as_of=datetime.now(timezone.utc),
    )
    with pytest.raises((AttributeError, TypeError)):
        ctx.trend_regime = "downtrend"  # type: ignore[misc]


def test_to_dict_has_all_keys():
    ctx = RegimeContext(
        trend_regime="range",
        volatility_regime="low",
        liquidity_regime="medium",
        event_regime="normal",
        market_state="range_low_vol_medium_liq",
        source_version="v1",
        as_of=datetime.now(timezone.utc),
    )
    d = ctx.to_dict()
    assert set(d) == {
        "trend_regime", "volatility_regime", "liquidity_regime",
        "event_regime", "market_state", "source_version", "as_of",
    }
    assert d["trend_regime"] == "range"
    assert d["as_of"].endswith("+00:00") or "T" in d["as_of"]


# ---------------------------------------------------------------------------
# Normalization mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("market_regime, expected_trend, expected_vol", [
    (MarketRegime.TRENDING_UP, "uptrend", "medium"),
    (MarketRegime.TRENDING_DOWN, "downtrend", "medium"),
    (MarketRegime.SIDEWAYS, "range", "medium"),
    (MarketRegime.HIGH_VOLATILITY, "range", "high"),
    (MarketRegime.LOW_VOLATILITY, "range", "low"),
    (MarketRegime.UNKNOWN, "unknown", "unknown"),
])
def test_normalize_equity_mapping(market_regime, expected_trend, expected_vol):
    ctx = _normalize_equity(market_regime)
    assert ctx.trend_regime == expected_trend
    assert ctx.volatility_regime == expected_vol


def test_normalize_equity_market_state_format():
    ctx = _normalize_equity(MarketRegime.TRENDING_UP)
    assert ctx.market_state == "uptrend_medium_vol_medium_liq"


def test_unknown_context_fields():
    ctx = _unknown_context()
    assert ctx.trend_regime == "unknown"
    assert ctx.volatility_regime == "unknown"
    assert ctx.liquidity_regime == "unknown"
    assert ctx.event_regime == "normal"


# ---------------------------------------------------------------------------
# Prediction market context
# ---------------------------------------------------------------------------


def test_resolve_from_liquidity_favorable():
    resolver = RegimeContextResolver()
    ctx = resolver.resolve_from_liquidity(LiquidityRegime.FAVORABLE, "SOME-TICKER")
    assert ctx.trend_regime == "n/a"
    assert ctx.volatility_regime == "n/a"
    assert ctx.liquidity_regime == "high"
    assert "prediction_market" in ctx.market_state


def test_resolve_from_liquidity_unfavorable():
    resolver = RegimeContextResolver()
    ctx = resolver.resolve_from_liquidity(LiquidityRegime.UNFAVORABLE, "SOME-TICKER")
    assert ctx.liquidity_regime == "low"


def test_resolve_from_liquidity_unknown():
    resolver = RegimeContextResolver()
    ctx = resolver.resolve_from_liquidity(LiquidityRegime.UNKNOWN, "SOME-TICKER")
    assert ctx.liquidity_regime == "medium"


# ---------------------------------------------------------------------------
# RegimeContextResolver — equity path
# ---------------------------------------------------------------------------


def test_resolve_from_regime_returns_context():
    resolver = RegimeContextResolver()
    ctx = resolver.resolve_from_regime(MarketRegime.TRENDING_UP)
    assert isinstance(ctx, RegimeContext)
    assert ctx.trend_regime == "uptrend"


def test_resolve_from_snapshot_none_returns_unknown():
    resolver = RegimeContextResolver()
    ctx = resolver.resolve_from_snapshot(None)
    assert ctx.trend_regime == "unknown"


def test_resolve_unknown():
    resolver = RegimeContextResolver()
    ctx = resolver.resolve_unknown()
    assert ctx.trend_regime == "unknown"
    assert ctx.source_version == "v1"


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


def test_cache_hit_returns_same_object():
    resolver = RegimeContextResolver(ttl_seconds=60)
    ctx1 = resolver.resolve_from_regime(MarketRegime.TRENDING_UP, cache_key="spy")
    ctx2 = resolver.resolve_from_regime(MarketRegime.TRENDING_DOWN, cache_key="spy")
    # Second call should return cached result (TRENDING_UP), not TRENDING_DOWN
    assert ctx1 is ctx2
    assert ctx2.trend_regime == "uptrend"


def test_cache_expires_after_ttl():
    resolver = RegimeContextResolver(ttl_seconds=0)  # TTL=0 → always miss
    ctx1 = resolver.resolve_from_regime(MarketRegime.TRENDING_UP, cache_key="spy")
    ctx2 = resolver.resolve_from_regime(MarketRegime.TRENDING_DOWN, cache_key="spy")
    assert ctx1 is not ctx2
    assert ctx2.trend_regime == "downtrend"


def test_cache_invalidate():
    resolver = RegimeContextResolver(ttl_seconds=60)
    resolver.resolve_from_regime(MarketRegime.TRENDING_UP, cache_key="spy")
    resolver.invalidate("spy")
    ctx = resolver.resolve_from_regime(MarketRegime.SIDEWAYS, cache_key="spy")
    assert ctx.trend_regime == "range"


def test_prediction_market_cache_is_per_symbol():
    resolver = RegimeContextResolver(ttl_seconds=60)
    ctx_a = resolver.resolve_from_liquidity(LiquidityRegime.FAVORABLE, "AAA")
    ctx_b = resolver.resolve_from_liquidity(LiquidityRegime.UNFAVORABLE, "BBB")
    assert ctx_a.liquidity_regime == "high"
    assert ctx_b.liquidity_regime == "low"


# ---------------------------------------------------------------------------
# Same inputs always produce the same labels (determinism)
# ---------------------------------------------------------------------------


def test_normalization_is_deterministic():
    ctx1 = _normalize_equity(MarketRegime.HIGH_VOLATILITY)
    ctx2 = _normalize_equity(MarketRegime.HIGH_VOLATILITY)
    assert ctx1.trend_regime == ctx2.trend_regime
    assert ctx1.volatility_regime == ctx2.volatility_regime
    assert ctx1.market_state == ctx2.market_state
