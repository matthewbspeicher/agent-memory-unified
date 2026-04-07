"""Tests for Alpha Token Strategy."""

import pytest
from datetime import datetime

from strategy.alpha_token import (
    AlphaTokenState,
    AlphaTokenStrategy,
    StakingRecommendation,
)


class TestAlphaTokenStrategy:
    def test_init(self):
        strategy = AlphaTokenStrategy()
        assert strategy.min_stake_ratio == 0.3
        assert strategy.max_stake_ratio == 0.8
        assert strategy.target_stake_ratio == 0.5

    def test_recommendation_hold_no_state(self):
        strategy = AlphaTokenStrategy()
        rec = strategy.get_recommendation(current_stake=1000)

        assert rec.action == "hold"
        assert rec.confidence == 0.0

    def test_recommendation_stake_high_demand(self):
        strategy = AlphaTokenStrategy()
        state = AlphaTokenState(
            price_usd=0.05,
            market_cap=1_000_000,
            staking_ratio=0.4,
            daily_rewards=100,
            validator_count=20,
            network_demand=0.8,  # High demand
            last_update=datetime.now(),
        )
        strategy.update_state(state)

        # Current ratio ~0.5 (1000/20000), target 0.5, demand high
        rec = strategy.get_recommendation(current_stake=1000)

        assert rec.action == "stake"
        assert rec.amount_alpha > 0

    def test_recommendation_unstake_low_demand(self):
        strategy = AlphaTokenStrategy()
        state = AlphaTokenState(
            price_usd=0.05,
            market_cap=1_000_000,
            staking_ratio=0.7,
            daily_rewards=100,
            validator_count=20,
            network_demand=0.2,  # Low demand
            last_update=datetime.now(),
        )
        strategy.update_state(state)

        # With 20 validators * 10000 = 200000 total, stake 120000 = 60% ratio
        # Above target 50% and low demand -> unstake
        rec = strategy.get_recommendation(current_stake=120000)

        assert rec.action == "unstake"
        assert rec.amount_alpha > 0

    def test_recommendation_hold_moderate(self):
        strategy = AlphaTokenStrategy()
        state = AlphaTokenState(
            price_usd=0.05,
            market_cap=1_000_000,
            staking_ratio=0.5,
            daily_rewards=100,
            validator_count=20,
            network_demand=0.5,  # Moderate
            last_update=datetime.now(),
        )
        strategy.update_state(state)

        rec = strategy.get_recommendation(current_stake=10000)

        assert rec.action == "hold"

    def test_analyze_utility(self):
        strategy = AlphaTokenStrategy()
        state = AlphaTokenState(
            price_usd=0.05,
            market_cap=1_000_000,
            staking_ratio=0.5,
            daily_rewards=100,
            validator_count=20,
            network_demand=0.7,
            last_update=datetime.now(),
        )
        strategy.update_state(state)

        utility = strategy.analyze_utility()

        assert "utility_score" in utility
        assert utility["utility_score"] > 0
        assert "factors" in utility
        assert len(utility["factors"]) > 0


class TestStakingRecommendation:
    def test_recommendation_fields(self):
        rec = StakingRecommendation(
            action="stake",
            amount_alpha=1000,
            reason="Test",
            expected_apr=0.15,
            confidence=0.8,
        )

        assert rec.action == "stake"
        assert rec.amount_alpha == 1000
        assert rec.expected_apr == 0.15
        assert rec.confidence == 0.8
