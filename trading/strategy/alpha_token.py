"""dTAO Alpha Token Strategy for Vanta Network.

Monitors Vanta Alpha token economics and provides:
- Staking recommendations based on network demand
- Validator reward optimization
- Alpha token utility tracking

Reference: Vanta Network docs on tokenomics
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlphaTokenState:
    """Current state of Alpha token."""

    price_usd: float | None
    market_cap: float | None
    staking_ratio: float | None  # % of tokens staked
    daily_rewards: float | None
    validator_count: int
    network_demand: float  # 0-1 scale
    last_update: datetime


@dataclass
class StakingRecommendation:
    """Recommendation for Alpha token staking."""

    action: str  # "stake", "unstake", "hold"
    amount_alpha: float  # Amount in Alpha tokens
    reason: str
    expected_apr: float | None
    confidence: float  # 0-1


class AlphaTokenStrategy:
    """Strategy for optimizing Alpha token staking.

    Analyzes network metrics and tokenomics to recommend
    staking/unstaking decisions for validator reward optimization.
    """

    def __init__(
        self,
        min_stake_ratio: float = 0.3,
        max_stake_ratio: float = 0.8,
        target_stake_ratio: float = 0.5,
    ):
        self.min_stake_ratio = min_stake_ratio
        self.max_stake_ratio = max_stake_ratio
        self.target_stake_ratio = target_stake_ratio

        self._state: AlphaTokenState | None = None

    def update_state(self, state: AlphaTokenState) -> None:
        """Update with new token state."""
        self._state = state
        logger.debug(
            "Alpha token state updated: price=$%.4f, validators=%d, demand=%.2f",
            state.price_usd or 0,
            state.validator_count,
            state.network_demand,
        )

    def get_recommendation(self, current_stake: float) -> StakingRecommendation:
        """Get staking recommendation based on current state.

        Args:
            current_stake: Current amount of Alpha staked

        Returns:
            StakingRecommendation
        """
        if self._state is None:
            return StakingRecommendation(
                action="hold",
                amount_alpha=0,
                reason="No token state data available",
                expected_apr=None,
                confidence=0.0,
            )

        state = self._state

        # Calculate current stake ratio (estimate based on validator count)
        # In reality, would query chain for actual stake
        estimated_total_stake = state.validator_count * 10000  # rough estimate
        current_ratio = (
            current_stake / estimated_total_stake if estimated_total_stake > 0 else 0.5
        )

        # High demand + low stake ratio = stake more
        if state.network_demand > 0.7 and current_ratio < self.target_stake_ratio:
            # Network is busy, validators need more stake for priority
            stake_amount = estimated_total_stake * (
                self.target_stake_ratio - current_ratio
            )
            return StakingRecommendation(
                action="stake",
                amount_alpha=max(stake_amount, 100),  # Minimum 100 Alpha
                reason=f"High network demand ({state.network_demand:.0%}), stake for priority",
                expected_apr=self._estimate_apr(state),
                confidence=0.7,
            )

        # Low demand + high stake ratio = unstake some
        if state.network_demand < 0.3 and current_ratio > self.target_stake_ratio:
            unstake_amount = current_stake * (current_ratio - self.target_stake_ratio)
            return StakingRecommendation(
                action="unstake",
                amount_alpha=unstake_amount,
                reason=f"Low network demand ({state.network_demand:.0%}), reduce stake to improve liquidity",
                expected_apr=None,
                confidence=0.6,
            )

        # Default: hold
        return StakingRecommendation(
            action="hold",
            amount_alpha=0,
            reason="Network demand is moderate, maintain current stake",
            expected_apr=self._estimate_apr(state) if state.price_usd else None,
            confidence=0.5,
        )

    def _estimate_apr(self, state: AlphaTokenState) -> float | None:
        """Estimate APR based on token state."""
        if state.daily_rewards is None or state.price_usd is None:
            return None

        # Rough APR calculation: daily_rewards * 365 / market_cap
        if state.market_cap and state.market_cap > 0:
            return (state.daily_rewards * 365) / state.market_cap * 100

        return None

    def analyze_utility(self) -> dict[str, Any]:
        """Analyze Alpha token utility metrics.

        Returns:
            Dict with utility analysis
        """
        if self._state is None:
            return {"status": "no_data"}

        state = self._state

        # Score utility factors
        utility_score = 0.0
        factors = []

        # Demand factor
        if state.network_demand > 0.6:
            utility_score += 0.4
            factors.append("high_demand")
        elif state.network_demand > 0.3:
            utility_score += 0.2
            factors.append("moderate_demand")
        else:
            factors.append("low_demand")

        # Staking ratio factor (healthy = not too high, not too low)
        if state.staking_ratio:
            if 0.4 <= state.staking_ratio <= 0.7:
                utility_score += 0.3
                factors.append("healthy_stake_ratio")
            elif state.staking_ratio > 0.8:
                utility_score += 0.1
                factors.append("high_stake_ratio")
            else:
                factors.append("low_stake_ratio")

        # Validator count factor
        if state.validator_count > 10:
            utility_score += 0.2
            factors.append("good_validator_count")
        elif state.validator_count > 3:
            utility_score += 0.1
            factors.append("moderate_validators")
        else:
            factors.append("few_validators")

        # Price factor (if available and reasonable)
        if state.price_usd and state.price_usd > 0.001:
            utility_score += 0.1
            factors.append("price_established")

        return {
            "utility_score": min(utility_score, 1.0),
            "factors": factors,
            "network_demand": state.network_demand,
            "validator_count": state.validator_count,
            "estimated_apr": self._estimate_apr(state),
            "last_update": state.last_update.isoformat() if state.last_update else None,
        }
