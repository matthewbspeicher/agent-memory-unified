"""Tests for RegimeFilter — TDD phase."""
import pytest
from regime.models import MarketRegime
from regime.agent_filter import RegimeFilter


class TestRegimeFilter:
    def test_trending_agent_allowed_in_trending_up(self):
        filt = RegimeFilter()
        # Trend-following agents should work in trending markets
        assert filt.is_allowed("momentum_agent", MarketRegime.TRENDING_UP) is True

    def test_all_agents_blocked_in_high_volatility_by_default(self):
        """By default, no agents are configured to run in HIGH_VOLATILITY."""
        filt = RegimeFilter()
        # Default: conservative — block all in HIGH_VOLATILITY
        assert filt.is_allowed("any_agent", MarketRegime.HIGH_VOLATILITY) is False

    def test_unknown_regime_allows_all(self):
        """When regime is UNKNOWN (not enough data), allow all trades."""
        filt = RegimeFilter()
        assert filt.is_allowed("any_agent", MarketRegime.UNKNOWN) is True

    def test_custom_allowed_regimes(self):
        """Agents can be configured with custom allowed regime lists."""
        filt = RegimeFilter(
            agent_regimes={
                "vol_arb_agent": {MarketRegime.HIGH_VOLATILITY, MarketRegime.SIDEWAYS},
            }
        )
        assert filt.is_allowed("vol_arb_agent", MarketRegime.HIGH_VOLATILITY) is True
        assert filt.is_allowed("vol_arb_agent", MarketRegime.TRENDING_UP) is False

    def test_sideways_agent_blocked_in_trending(self):
        """Mean-reversion agent blocked in trending regime."""
        filt = RegimeFilter(
            agent_regimes={
                "mean_rev_agent": {MarketRegime.SIDEWAYS, MarketRegime.LOW_VOLATILITY},
            }
        )
        assert filt.is_allowed("mean_rev_agent", MarketRegime.TRENDING_UP) is False
        assert filt.is_allowed("mean_rev_agent", MarketRegime.SIDEWAYS) is True

    def test_unlisted_agent_uses_default(self):
        """Agents not in the custom map use the default allowed set."""
        filt = RegimeFilter(
            agent_regimes={
                "special_agent": {MarketRegime.TRENDING_UP},
            }
        )
        # unlisted_agent should use default (trending regimes)
        assert filt.is_allowed("unlisted_agent", MarketRegime.TRENDING_UP) is True
        assert filt.is_allowed("unlisted_agent", MarketRegime.HIGH_VOLATILITY) is False

    def test_all_regimes_blocked_except_sideways(self):
        """Agent configured to only trade sideways markets."""
        filt = RegimeFilter(
            agent_regimes={
                "range_trader": {MarketRegime.SIDEWAYS},
            }
        )
        for regime in MarketRegime:
            if regime == MarketRegime.SIDEWAYS:
                assert filt.is_allowed("range_trader", regime) is True
            elif regime == MarketRegime.UNKNOWN:
                assert filt.is_allowed("range_trader", regime) is True
            else:
                assert filt.is_allowed("range_trader", regime) is False
