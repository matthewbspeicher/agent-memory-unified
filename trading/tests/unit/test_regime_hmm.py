"""Tests for HMM-based regime detection in RegimeMemoryManager."""

import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import datetime, timezone

from memory.market_regime import RegimeMemoryManager


def _make_bars(prices: list[float]):
    from broker.models import Bar, Symbol, AssetType
    from datetime import timedelta

    base = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    return [
        Bar(
            symbol=Symbol(ticker="BTCUSD", asset_type=AssetType.CRYPTO),
            timestamp=base + timedelta(hours=i),
            close=Decimal(str(p)),
        )
        for i, p in enumerate(prices)
    ]


@pytest.fixture
def manager():
    client = MagicMock()
    return RegimeMemoryManager(client=client)


def test_too_few_bars_returns_unknown(manager):
    bars = _make_bars([100.0])
    assert manager.detect_regime(bars) == "unknown"


def test_heuristic_fallback_for_small_dataset(manager):
    """< 30 bars uses heuristic, not HMM."""
    # Steadily rising prices (10 bars)
    bars = _make_bars([100 + i * 0.5 for i in range(10)])
    result = manager.detect_regime(bars)
    # Should detect a trend (heuristic path)
    assert result in ("trending_bull", "volatile_uptrend")


def test_hmm_detects_trending_bull(manager):
    """30+ bars of steady uptrend should detect bullish regime."""
    # Simulate trending bull: steady small positive returns
    prices = [100.0]
    for _ in range(50):
        prices.append(prices[-1] * 1.002)  # +0.2% per bar
    bars = _make_bars(prices)
    result = manager.detect_regime(bars)
    assert result in ("trending_bull", "volatile_uptrend"), f"Got {result}"


def test_hmm_detects_trending_bear(manager):
    """30+ bars of steady downtrend should detect bearish regime."""
    prices = [100.0]
    for _ in range(50):
        prices.append(prices[-1] * 0.998)  # -0.2% per bar
    bars = _make_bars(prices)
    result = manager.detect_regime(bars)
    assert result in ("trending_bear", "volatile_downtrend"), f"Got {result}"


def test_hmm_detects_quiet_or_volatile(manager):
    """Sideways market should detect range-bound regime."""
    import random

    random.seed(42)
    prices = [100.0]
    for _ in range(50):
        prices.append(prices[-1] * (1 + random.gauss(0, 0.001)))
    bars = _make_bars(prices)
    result = manager.detect_regime(bars)
    assert result in ("quiet_range", "volatile_range"), f"Got {result}"


def test_hmm_returns_valid_regime_label(manager):
    """Whatever the data, result should be a known regime label."""
    import random

    random.seed(123)
    prices = [100.0]
    for _ in range(60):
        prices.append(prices[-1] * (1 + random.gauss(0, 0.01)))
    bars = _make_bars(prices)
    result = manager.detect_regime(bars)
    valid = {
        "trending_bull",
        "trending_bear",
        "quiet_range",
        "volatile_range",
        "volatile_uptrend",
        "volatile_downtrend",
        "unknown",
    }
    assert result in valid, f"Got unexpected regime: {result}"


def test_heuristic_method_directly(manager):
    """Test the static heuristic method independently."""
    # Strong positive returns
    returns = [0.01] * 20
    assert manager._detect_regime_heuristic(returns) in (
        "trending_bull",
        "volatile_uptrend",
    )

    # Strong negative returns
    returns = [-0.01] * 20
    assert manager._detect_regime_heuristic(returns) in (
        "trending_bear",
        "volatile_downtrend",
    )

    # Near-zero returns, low vol
    returns = [0.0001, -0.0001] * 10
    assert manager._detect_regime_heuristic(returns) == "quiet_range"
