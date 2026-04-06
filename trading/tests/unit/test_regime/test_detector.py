"""Tests for RegimeDetector — TDD phase."""

from datetime import datetime, timezone
from decimal import Decimal

from regime.models import MarketRegime
from regime.detector import RegimeDetector


def _make_bar(
    close: float,
    high: float | None = None,
    low: float | None = None,
    ts: datetime | None = None,
):
    """Create a minimal bar dict for testing."""
    from broker.models import Bar, Symbol, AssetType

    return Bar(
        symbol=Symbol(ticker="SPY", asset_type=AssetType.STOCK),
        timestamp=ts or datetime.now(timezone.utc),
        open=Decimal(str(close)),
        high=Decimal(str(high or close * 1.01)),
        low=Decimal(str(low or close * 0.99)),
        close=Decimal(str(close)),
        volume=1000000,
    )


def _trending_up_bars(n: int = 60) -> list:
    """Generate strongly trending up bars."""
    bars = []
    for i in range(n):
        close = 400.0 + i * 2.0  # Strong uptrend
        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        bars.append(_make_bar(close, ts=ts))
    return bars


def _sideways_bars(n: int = 60) -> list:
    """Generate sideways/choppy bars."""
    bars = []
    import math

    for i in range(n):
        close = 400.0 + math.sin(i * 0.5) * 2.0  # Oscillates ±2 around 400
        bars.append(_make_bar(close))
    return bars


def _volatile_bars(n: int = 60) -> list:
    """Generate high volatility bars (large ranges)."""
    bars = []
    for i in range(n):
        close = 400.0 + (i % 2) * 5.0  # Alternating 400 and 405
        high = close + 10.0
        low = close - 10.0  # Wide range = high volatility
        bars.append(_make_bar(close, high=high, low=low))
    return bars


class TestRegimeDetector:
    def test_detect_returns_market_regime(self):
        detector = RegimeDetector()
        bars = _trending_up_bars(60)
        regime = detector.detect(bars)
        assert isinstance(regime, MarketRegime)

    def test_trending_up_bars_detected(self):
        detector = RegimeDetector()
        bars = _trending_up_bars(60)
        regime = detector.detect(bars)
        assert regime == MarketRegime.TRENDING_UP

    def test_sideways_bars_detected(self):
        detector = RegimeDetector()
        bars = _sideways_bars(60)
        regime = detector.detect(bars)
        assert regime in (MarketRegime.SIDEWAYS, MarketRegime.LOW_VOLATILITY)

    def test_insufficient_bars_returns_unknown(self):
        detector = RegimeDetector()
        bars = _make_bar(400.0)  # Only 1 bar
        regime = detector.detect([bars])
        assert regime == MarketRegime.UNKNOWN

    def test_empty_bars_returns_unknown(self):
        detector = RegimeDetector()
        regime = detector.detect([])
        assert regime == MarketRegime.UNKNOWN

    def test_volatile_bars_detected(self):
        detector = RegimeDetector()
        bars = _volatile_bars(60)
        regime = detector.detect(bars)
        assert regime in (
            MarketRegime.HIGH_VOLATILITY,
            MarketRegime.TRENDING_DOWN,
            MarketRegime.SIDEWAYS,
        )
        # Volatile bars should not be TRENDING_UP or LOW_VOLATILITY

    def test_trending_down_bars(self):
        detector = RegimeDetector()
        bars = []
        for i in range(60):
            close = 500.0 - i * 2.0  # Strong downtrend
            bars.append(_make_bar(close))
        regime = detector.detect(bars)
        assert regime == MarketRegime.TRENDING_DOWN
