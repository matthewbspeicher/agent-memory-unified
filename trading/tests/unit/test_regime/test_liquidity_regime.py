"""Tests for LiquidityRegimeDetector and per-symbol RegimeFilter liquidity checks."""

from __future__ import annotations
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from regime.models import LiquidityRegime, LiquiditySnapshot
from regime.detector import LiquidityRegimeDetector
from regime.agent_filter import RegimeFilter
from broker.models import Symbol, AssetType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_symbol(ticker: str, asset_type: AssetType = AssetType.PREDICTION) -> Symbol:
    return Symbol(ticker=ticker, asset_type=asset_type)


def _make_quote(bid: float, ask: float, volume: float = 5000.0):
    q = MagicMock()
    q.bid = bid
    q.ask = ask
    q.volume = volume
    return q


def _make_source(quote=None, markets=None):
    source = MagicMock()
    source.get_quote = AsyncMock(return_value=quote)
    source.get_markets = AsyncMock(return_value=markets or [])
    return source


# ---------------------------------------------------------------------------
# LiquidityRegimeDetector — detect_symbol
# ---------------------------------------------------------------------------


class TestDetectSymbol:
    @pytest.mark.asyncio
    async def test_tight_spread_high_volume_returns_favorable(self):
        """bid=0.48, ask=0.52 → spread=4¢, vol=5000 → FAVORABLE (defaults: max=5¢, min=1000)."""
        quote = _make_quote(bid=0.48, ask=0.52, volume=5000)
        source = _make_source(quote=quote)
        detector = LiquidityRegimeDetector(kalshi_source=source)

        sym = _make_symbol("KXBTC-23")
        result = await detector.detect_symbol(sym)

        assert result.regime == LiquidityRegime.FAVORABLE
        assert result.spread_cents == pytest.approx(4.0, abs=0.01)
        assert result.volume_24h == 5000.0
        assert result.symbol == "KXBTC-23"

    @pytest.mark.asyncio
    async def test_wide_spread_returns_unfavorable(self):
        """spread > 5¢ → UNFAVORABLE regardless of volume."""
        quote = _make_quote(bid=0.40, ask=0.47, volume=10000)  # spread = 7¢
        source = _make_source(quote=quote)
        detector = LiquidityRegimeDetector(kalshi_source=source)

        sym = _make_symbol("KXSPR-99")
        result = await detector.detect_symbol(sym)

        assert result.regime == LiquidityRegime.UNFAVORABLE
        assert result.spread_cents == pytest.approx(7.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_low_volume_returns_unfavorable(self):
        """volume < 1000 → UNFAVORABLE regardless of spread."""
        quote = _make_quote(bid=0.49, ask=0.51, volume=500)  # spread = 2¢, vol low
        source = _make_source(quote=quote)
        detector = LiquidityRegimeDetector(kalshi_source=source)

        sym = _make_symbol("KXLOW-01")
        result = await detector.detect_symbol(sym)

        assert result.regime == LiquidityRegime.UNFAVORABLE

    @pytest.mark.asyncio
    async def test_no_source_returns_unknown(self):
        """No source configured → UNKNOWN (fail-open)."""
        detector = LiquidityRegimeDetector()  # both sources None

        sym = _make_symbol("KXNONE-1")
        result = await detector.detect_symbol(sym)

        assert result.regime == LiquidityRegime.UNKNOWN
        assert result.spread_cents == 0.0
        assert result.volume_24h == 0.0

    @pytest.mark.asyncio
    async def test_source_returns_none_quote_gives_unknown(self):
        """Source returns None quote → UNKNOWN (fail-open)."""
        source = _make_source(quote=None)
        detector = LiquidityRegimeDetector(kalshi_source=source)

        sym = _make_symbol("KXNULL-1")
        result = await detector.detect_symbol(sym)

        assert result.regime == LiquidityRegime.UNKNOWN

    @pytest.mark.asyncio
    async def test_source_raises_exception_gives_unknown(self):
        """Source raises exception → UNKNOWN (fail-open)."""
        source = MagicMock()
        source.get_quote = AsyncMock(side_effect=RuntimeError("connection refused"))
        detector = LiquidityRegimeDetector(kalshi_source=source)

        sym = _make_symbol("KXERR-1")
        result = await detector.detect_symbol(sym)

        assert result.regime == LiquidityRegime.UNKNOWN

    # ------------------------------------------------------------------
    # Cache behaviour
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cache_hit_within_ttl_returns_cached_result(self):
        """Second call within TTL returns cached snapshot without hitting source."""
        quote = _make_quote(bid=0.48, ask=0.52, volume=5000)
        source = _make_source(quote=quote)
        detector = LiquidityRegimeDetector(kalshi_source=source, cache_ttl_seconds=300)

        sym = _make_symbol("KXCACHE-1")
        first = await detector.detect_symbol(sym)
        second = await detector.detect_symbol(sym)

        assert first is second  # same object returned from cache
        source.get_quote.assert_called_once()  # only one remote call

    @pytest.mark.asyncio
    async def test_cache_miss_after_ttl_fetches_fresh_data(self):
        """After TTL expires the detector fetches fresh data."""
        quote = _make_quote(bid=0.48, ask=0.52, volume=5000)
        source = _make_source(quote=quote)
        detector = LiquidityRegimeDetector(kalshi_source=source, cache_ttl_seconds=60)

        sym = _make_symbol("KXSTALE-1")
        first = await detector.detect_symbol(sym)

        # Manually expire the cache entry
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        detector._cache[sym.ticker] = LiquiditySnapshot(
            regime=first.regime,
            spread_cents=first.spread_cents,
            volume_24h=first.volume_24h,
            symbol=first.symbol,
            detected_at=stale_time,
        )

        second = await detector.detect_symbol(sym)

        assert second is not first  # new object
        assert source.get_quote.call_count == 2  # fetched twice


# ---------------------------------------------------------------------------
# RegimeFilter — per-symbol liquidity (async)
# ---------------------------------------------------------------------------


class TestRegimeFilterPerSymbol:
    @pytest.mark.asyncio
    async def test_prediction_agent_blocked_when_symbol_unfavorable(self):
        """UNFAVORABLE liquidity snapshot blocks a prediction agent."""
        unfavorable = LiquiditySnapshot(
            regime=LiquidityRegime.UNFAVORABLE,
            spread_cents=8.0,
            volume_24h=200,
            symbol="KXBAD-1",
            detected_at=datetime.now(),
        )
        detector = MagicMock()
        detector.detect_symbol = AsyncMock(return_value=unfavorable)

        filt = RegimeFilter(liquidity_detector=detector)
        sym = _make_symbol("KXBAD-1", asset_type=AssetType.PREDICTION)

        allowed = await filt.is_allowed_for_symbol("pred_agent", sym)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_prediction_agent_allowed_when_symbol_favorable(self):
        """FAVORABLE liquidity allows a prediction agent."""
        favorable = LiquiditySnapshot(
            regime=LiquidityRegime.FAVORABLE,
            spread_cents=2.0,
            volume_24h=8000,
            symbol="KXGOOD-1",
            detected_at=datetime.now(),
        )
        detector = MagicMock()
        detector.detect_symbol = AsyncMock(return_value=favorable)

        filt = RegimeFilter(liquidity_detector=detector)
        sym = _make_symbol("KXGOOD-1", asset_type=AssetType.PREDICTION)

        allowed = await filt.is_allowed_for_symbol("pred_agent", sym)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_unknown_regime_allows_prediction_agent(self):
        """UNKNOWN liquidity → fail-open → allow."""
        unknown = LiquiditySnapshot(
            regime=LiquidityRegime.UNKNOWN,
            spread_cents=0.0,
            volume_24h=0.0,
            symbol="KXUNK-1",
            detected_at=datetime.now(),
        )
        detector = MagicMock()
        detector.detect_symbol = AsyncMock(return_value=unknown)

        filt = RegimeFilter(liquidity_detector=detector)
        sym = _make_symbol("KXUNK-1", asset_type=AssetType.PREDICTION)

        allowed = await filt.is_allowed_for_symbol("pred_agent", sym)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_stock_agent_unaffected_by_liquidity_regime(self):
        """Non-prediction symbols use the equity regime path, not liquidity."""
        detector = MagicMock()
        detector.detect_symbol = AsyncMock()  # should never be called

        filt = RegimeFilter(liquidity_detector=detector)
        stock_sym = _make_symbol("AAPL", asset_type=AssetType.STOCK)

        # is_allowed_for_symbol for a STOCK symbol returns True (caller uses is_allowed)
        allowed = await filt.is_allowed_for_symbol("momentum_agent", stock_sym)
        assert allowed is True
        detector.detect_symbol.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_liquidity_detector_allows_all_prediction_agents(self):
        """When no detector is configured, prediction agents are always allowed."""
        filt = RegimeFilter()  # no liquidity_detector
        sym = _make_symbol("KXNODET-1", asset_type=AssetType.PREDICTION)

        allowed = await filt.is_allowed_for_symbol("pred_agent", sym)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_detector_exception_fails_open(self):
        """Unexpected exception from detector → fail-open → allow."""
        detector = MagicMock()
        detector.detect_symbol = AsyncMock(side_effect=RuntimeError("boom"))

        filt = RegimeFilter(liquidity_detector=detector)
        sym = _make_symbol("KXFAIL-1", asset_type=AssetType.PREDICTION)

        allowed = await filt.is_allowed_for_symbol("pred_agent", sym)
        assert allowed is True

    def test_existing_equity_is_allowed_unchanged(self):
        """Existing synchronous is_allowed() continues to work for equity regime checks."""
        from regime.models import MarketRegime

        filt = RegimeFilter()
        assert filt.is_allowed("momentum_agent", MarketRegime.TRENDING_UP) is True
        assert filt.is_allowed("momentum_agent", MarketRegime.HIGH_VOLATILITY) is False
        assert filt.is_allowed("any_agent", MarketRegime.UNKNOWN) is True
