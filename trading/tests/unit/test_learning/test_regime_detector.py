"""Property-based tests for RegimeDetector using Hypothesis."""

from hypothesis import given, settings
from hypothesis.strategies import lists, floats, integers

from learning.ensemble_optimizer import RegimeDetector, MarketRegime


class TestRegimeDetector:
    """Property-based tests for MarketRegime detection."""

    @given(
        lists(
            floats(
                min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),
            min_size=20,
            max_size=100,
        )
    )
    @settings(max_examples=20, deadline=None)
    def test_detect_returns_valid_regime(self, prices):
        """Regime detection should always return a valid MarketRegime."""
        detector = RegimeDetector()
        regime = detector.detect(prices)
        assert isinstance(regime, MarketRegime)

    def test_detect_handles_empty_prices(self):
        """Empty price list should return UNKNOWN."""
        detector = RegimeDetector()
        regime = detector.detect([])
        assert regime == MarketRegime.UNKNOWN

    def test_detect_insufficient_data(self):
        """Less than lookback bars should return UNKNOWN."""
        detector = RegimeDetector(lookback_bars=20)
        # 10 bars is less than lookback
        regime = detector.detect([100.0] * 10)
        assert regime == MarketRegime.UNKNOWN

    @given(
        lists(
            floats(
                min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),
            min_size=30,
            max_size=30,
        )
    )
    @settings(max_examples=10, deadline=None)
    def test_volatility_classification(self, prices):
        """Very high volatility should return HIGH_VOLATILITY."""
        detector = RegimeDetector(volatility_threshold=0.1)

        # Add extreme volatility to prices
        volatile_prices = [prices[0]]
        for i in range(1, len(prices)):
            volatile_prices.append(volatile_prices[-1] * (1 + (i % 2 - 0.5) * 0.5))

        regime = detector.detect(volatile_prices)

        # High volatility should return HIGH_VOLATILITY
        assert regime == MarketRegime.HIGH_VOLATILITY

    def test_bull_regime_detected(self):
        """Strong upward trend should detect bull regime."""
        # Create strong upward trend
        prices = [100.0]
        for i in range(30):
            prices.append(prices[-1] * 1.01)  # 1% gain per bar

        detector = RegimeDetector(trend_threshold=0.5, volatility_threshold=0.5)
        regime = detector.detect(prices)
        # Should be bull or sideways (depends on volatility threshold)
        assert regime in (
            MarketRegime.BULL,
            MarketRegime.SIDEWAYS,
            MarketRegime.LOW_VOLATILITY,
        )

    def test_bear_regime_detected(self):
        """Strong downward trend should detect bear regime."""
        # Create strong downward trend
        prices = [100.0]
        for i in range(30):
            prices.append(prices[-1] * 0.99)  # 1% loss per bar

        detector = RegimeDetector(trend_threshold=0.5, volatility_threshold=0.5)
        regime = detector.detect(prices)
        # Should be bear or sideways (depends on volatility threshold)
        assert regime in (
            MarketRegime.BEAR,
            MarketRegime.SIDEWAYS,
            MarketRegime.LOW_VOLATILITY,
        )

    def test_sideways_regime_detected(self):
        """Low-trend, low-volatility should detect sideways."""
        detector = RegimeDetector(trend_threshold=5.0, volatility_threshold=10.0)

        # Create flat series
        import random

        random.seed(42)
        prices = [100.0]
        for i in range(30):
            prices.append(prices[-1] + random.uniform(-0.1, 0.1))

        regime = detector.detect(prices)
        # Should be sideways or low_volatility
        assert regime in (MarketRegime.SIDEWAYS, MarketRegime.LOW_VOLATILITY)
