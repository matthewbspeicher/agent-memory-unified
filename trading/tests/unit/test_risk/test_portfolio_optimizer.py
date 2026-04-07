"""Tests for PortfolioOptimizer — risk parity, min-CVaR, max-Sharpe."""

import numpy as np
import pytest

from risk.portfolio_optimizer import PortfolioAllocation, PortfolioOptimizer


# ---------------------------------------------------------------------------
# Shared synthetic data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_returns() -> dict[str, list[float]]:
    """Three synthetic agents with 60 days of returns.

    - agent_a: slight positive drift, low vol (good Sharpe)
    - agent_b: higher returns, higher vol
    - agent_c: uncorrelated to both, slight positive
    """
    rng = np.random.default_rng(42)
    n = 60

    agent_a = (rng.normal(0.002, 0.008, n)).tolist()
    agent_b = (rng.normal(0.004, 0.020, n)).tolist()
    agent_c = (rng.normal(0.001, 0.012, n)).tolist()

    return {"agent_a": agent_a, "agent_b": agent_b, "agent_c": agent_c}


@pytest.fixture
def optimizer() -> PortfolioOptimizer:
    return PortfolioOptimizer(method="risk_parity", max_weight=0.40)


# ---------------------------------------------------------------------------
# Core constraint tests
# ---------------------------------------------------------------------------

class TestRiskParityConstraints:

    def test_risk_parity_weights_sum_to_one(self, optimizer, synthetic_returns):
        alloc = optimizer.optimize(synthetic_returns)
        total = sum(alloc.weights.values())
        assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, expected 1.0"

    def test_risk_parity_no_agent_exceeds_max(self, synthetic_returns):
        opt = PortfolioOptimizer(method="risk_parity", max_weight=0.40)
        alloc = opt.optimize(synthetic_returns)
        for name, w in alloc.weights.items():
            assert w <= 0.40 + 1e-6, f"{name} weight {w} exceeds max 0.40"


# ---------------------------------------------------------------------------
# Method-specific tests
# ---------------------------------------------------------------------------

class TestMinCVaR:

    def test_min_cvar_reduces_tail_risk(self, synthetic_returns):
        """Min-CVaR should yield lower CVaR than equal weighting."""
        opt = PortfolioOptimizer(method="min_cvar", max_weight=0.60)
        alloc = opt.optimize(synthetic_returns)

        # Compare with equal-weight CVaR
        n_agents = len(synthetic_returns)
        equal_w = np.ones(n_agents) / n_agents
        names = list(synthetic_returns.keys())
        mat = PortfolioOptimizer._build_returns_matrix(synthetic_returns, names)
        equal_cvar = PortfolioOptimizer._compute_cvar(mat, equal_w)

        assert alloc.cvar_95 <= equal_cvar + 1e-6, (
            f"Min-CVaR allocation CVaR {alloc.cvar_95:.6f} should be <= "
            f"equal-weight CVaR {equal_cvar:.6f}"
        )


class TestMaxSharpe:

    def test_max_sharpe_positive_expected_return(self, synthetic_returns):
        """If all agents are profitable, max-Sharpe should have positive return."""
        opt = PortfolioOptimizer(method="max_sharpe", max_weight=0.60)
        alloc = opt.optimize(synthetic_returns)
        assert alloc.expected_return > 0, (
            f"Expected positive return, got {alloc.expected_return}"
        )


# ---------------------------------------------------------------------------
# Diversification
# ---------------------------------------------------------------------------

class TestDiversification:

    def test_diversification_ratio_above_one(self, synthetic_returns):
        """Uncorrelated agents should yield diversification ratio > 1."""
        opt = PortfolioOptimizer(method="risk_parity", max_weight=0.60)
        alloc = opt.optimize(synthetic_returns)
        assert alloc.diversification_ratio >= 1.0, (
            f"Diversification ratio {alloc.diversification_ratio} should be >= 1"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_single_agent_gets_full_weight(self):
        """With only one agent, it should get 100% weight."""
        rng = np.random.default_rng(42)
        returns = {"solo_agent": rng.normal(0.001, 0.01, 60).tolist()}
        opt = PortfolioOptimizer(method="risk_parity", max_weight=1.0)
        alloc = opt.optimize(returns)
        assert abs(alloc.weights["solo_agent"] - 1.0) < 1e-6

    def test_identical_returns_equal_weights(self):
        """All agents with identical returns → approximately equal weights."""
        rng = np.random.default_rng(42)
        base = rng.normal(0.001, 0.01, 60).tolist()
        returns = {"a": base[:], "b": base[:], "c": base[:]}
        opt = PortfolioOptimizer(method="risk_parity", max_weight=1.0)
        alloc = opt.optimize(returns)

        expected_w = 1.0 / 3.0
        for name, w in alloc.weights.items():
            assert abs(w - expected_w) < 0.05, (
                f"{name} weight {w:.4f} not close to {expected_w:.4f}"
            )

    def test_fallback_on_optimization_failure(self):
        """Bad data (constant returns → singular covariance) → equal weights."""
        returns = {
            "a": [0.0] * 60,
            "b": [0.0] * 60,
            "c": [0.0] * 60,
        }
        opt = PortfolioOptimizer(method="min_cvar", max_weight=0.60)
        alloc = opt.optimize(returns)

        expected_w = 1.0 / 3.0
        for name, w in alloc.weights.items():
            assert abs(w - expected_w) < 1e-6, (
                f"Fallback: {name} weight {w:.4f} should be {expected_w:.4f}"
            )
        assert alloc.method == "equal_weight_fallback"


# ---------------------------------------------------------------------------
# CVaR computation
# ---------------------------------------------------------------------------

class TestCVaRComputation:

    def test_cvar_computation(self):
        """Verify CVaR math on known data."""
        # 20 returns: -10, -9, ..., 0, 1, ..., 9
        returns = np.arange(-10, 10, dtype=float).reshape(20, 1)
        weights = np.array([1.0])

        # alpha=0.05 → bottom 5% = 1 observation = -10
        cvar = PortfolioOptimizer._compute_cvar(returns, weights, alpha=0.05)
        assert abs(cvar - 10.0) < 1e-6, f"CVaR should be 10.0, got {cvar}"

        # alpha=0.10 → bottom 10% = 2 observations = -10, -9 → mean = -9.5
        cvar_10 = PortfolioOptimizer._compute_cvar(returns, weights, alpha=0.10)
        assert abs(cvar_10 - 9.5) < 1e-6, f"CVaR@10% should be 9.5, got {cvar_10}"


# ---------------------------------------------------------------------------
# Dataclass completeness
# ---------------------------------------------------------------------------

class TestAllocationDataclass:

    def test_allocation_dataclass_fields(self, optimizer, synthetic_returns):
        alloc = optimizer.optimize(synthetic_returns)

        assert isinstance(alloc.weights, dict)
        assert len(alloc.weights) == 3
        assert isinstance(alloc.method, str)
        assert alloc.method in (
            "risk_parity", "min_cvar", "max_sharpe", "equal_weight_fallback"
        )
        assert isinstance(alloc.expected_return, float)
        assert isinstance(alloc.expected_volatility, float)
        assert isinstance(alloc.cvar_95, float)
        assert isinstance(alloc.diversification_ratio, float)
