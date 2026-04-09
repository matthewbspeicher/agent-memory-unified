# tests/unit/test_data/test_indicators.py
from datetime import datetime, timedelta
from decimal import Decimal
import pytest

from broker.models import Bar, Symbol
from data.indicators import (
    MACD,
    BollingerBands,
    compute_sma,
    compute_ema,
    compute_rsi,
    compute_macd,
    compute_bollinger,
)

_BASE_DT = datetime(2026, 1, 1)


def _make_bars(closes: list[float]) -> list[Bar]:
    """Helper: create Bar list from close prices."""
    sym = Symbol(ticker="TEST")
    return [
        Bar(
            symbol=sym,
            close=Decimal(str(c)),
            open=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            volume=1000,
            timestamp=_BASE_DT + timedelta(days=i),
        )
        for i, c in enumerate(closes)
    ]


class TestSMA:
    def test_basic(self):
        bars = _make_bars([10, 20, 30, 40, 50])
        assert compute_sma(bars, 3) == pytest.approx(40.0)  # (30+40+50)/3

    def test_period_equals_length(self):
        bars = _make_bars([10, 20, 30])
        assert compute_sma(bars, 3) == pytest.approx(20.0)

    def test_insufficient_bars_raises(self):
        bars = _make_bars([10, 20])
        with pytest.raises(ValueError, match="Need at least 3"):
            compute_sma(bars, 3)


class TestEMA:
    def test_basic(self):
        bars = _make_bars(
            [
                22,
                22.27,
                22.19,
                22.08,
                22.17,
                22.18,
                22.13,
                22.23,
                22.43,
                22.24,
                22.29,
                22.15,
            ]
        )
        result = compute_ema(bars, 10)
        assert isinstance(result, float)
        assert 22.0 < result < 23.0

    def test_insufficient_bars_raises(self):
        bars = _make_bars([1, 2, 3])
        with pytest.raises(ValueError):
            compute_ema(bars, 5)


class TestRSI:
    def test_all_gains_returns_100(self):
        bars = _make_bars([float(i) for i in range(1, 20)])
        assert compute_rsi(bars, 14) == pytest.approx(100.0)

    def test_all_losses_returns_near_zero(self):
        bars = _make_bars([float(20 - i) for i in range(20)])
        result = compute_rsi(bars, 14)
        assert result < 5.0

    def test_known_range(self):
        # Mixed prices should yield RSI between 0 and 100
        prices = [
            44,
            44.34,
            44.09,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
        ]
        bars = _make_bars(prices)
        result = compute_rsi(bars, 14)
        assert 0 < result < 100

    def test_insufficient_bars_raises(self):
        bars = _make_bars([1, 2, 3])
        with pytest.raises(ValueError):
            compute_rsi(bars, 14)


class TestMACD:
    def test_returns_macd_object(self):
        # 40 bars needed for slow(26) + signal(9)
        bars = _make_bars([100 + i * 0.5 for i in range(40)])
        result = compute_macd(bars)
        assert isinstance(result, MACD)
        assert isinstance(result.macd_line, float)
        assert isinstance(result.signal_line, float)
        assert result.histogram == pytest.approx(result.macd_line - result.signal_line)

    def test_insufficient_bars_raises(self):
        bars = _make_bars([1, 2, 3])
        with pytest.raises(ValueError):
            compute_macd(bars)


class TestBollinger:
    def test_structure(self):
        bars = _make_bars([20 + i * 0.1 for i in range(25)])
        result = compute_bollinger(bars, 20)
        assert isinstance(result, BollingerBands)
        assert result.upper > result.middle > result.lower

    def test_constant_prices_bands_equal_middle(self):
        bars = _make_bars([50.0] * 25)
        result = compute_bollinger(bars, 20)
        assert result.upper == pytest.approx(50.0)
        assert result.middle == pytest.approx(50.0)
        assert result.lower == pytest.approx(50.0)

    def test_insufficient_bars_raises(self):
        bars = _make_bars([1, 2, 3])
        with pytest.raises(ValueError):
            compute_bollinger(bars, 20)


def test_compute_vwap():
    from broker.models import Bar
    from decimal import Decimal
    from data.indicators import compute_vwap
    bars = [
        Bar(symbol='BTC', timestamp=0, open=100, high=105, low=95, close=100, volume=10),
        Bar(symbol='BTC', timestamp=1, open=100, high=110, low=100, close=105, volume=20),
    ]
    result = compute_vwap(bars)
    assert round(float(result), 4) == 103.3333
