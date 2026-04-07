"""Portfolio optimizer using riskfolio-lib for CVaR optimization and risk parity.

Supports three methods:
- risk_parity: Equal risk contribution from each agent (CVaR-based)
- min_cvar: Minimize Conditional VaR (tail risk)
- max_sharpe: Maximize Sharpe ratio (mean-variance)

Falls back to equal weights when optimization fails (singular matrix, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import riskfolio as rp

logger = logging.getLogger(__name__)

VALID_METHODS = ("risk_parity", "min_cvar", "max_sharpe")


@dataclass
class PortfolioAllocation:
    """Optimized allocation across agents."""

    weights: dict[str, float]  # agent_name -> weight (0 to 1, sums to 1)
    method: str  # "risk_parity", "min_cvar", "max_sharpe", "equal_weight_fallback"
    expected_return: float
    expected_volatility: float
    cvar_95: float  # Conditional VaR at 95%
    diversification_ratio: float  # > 1 means diversification benefit


class PortfolioOptimizer:
    """Optimizes capital allocation across trading agents.

    Uses riskfolio-lib under the hood. Applies min/max weight constraints
    and falls back to equal weighting on optimization failure.
    """

    def __init__(
        self,
        method: str = "risk_parity",
        min_weight: float = 0.0,
        max_weight: float = 0.40,
        risk_free_rate: float = 0.0,
    ) -> None:
        if method not in VALID_METHODS:
            raise ValueError(
                f"Unknown method {method!r}. Choose from {VALID_METHODS}"
            )
        self.method = method
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.risk_free_rate = risk_free_rate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        returns: dict[str, list[float]],
        agent_names: list[str] | None = None,
    ) -> PortfolioAllocation:
        """Compute optimal weights given return histories.

        Args:
            returns: Dict mapping agent names to their daily return series.
                     All series must be the same length.
            agent_names: Optional ordering of agents. If None, uses dict keys.

        Returns:
            PortfolioAllocation with optimal weights.
        """
        if agent_names is None:
            agent_names = list(returns.keys())

        n_agents = len(agent_names)

        # Edge case: single agent
        if n_agents == 1:
            name = agent_names[0]
            mat = self._build_returns_matrix(returns, agent_names)
            w_arr = np.array([1.0])
            return self._build_allocation(
                mat, w_arr, agent_names, method=self.method
            )

        mat = self._build_returns_matrix(returns, agent_names)

        # Check for degenerate data (zero variance → singular covariance)
        if np.all(mat.std(axis=0) == 0):
            logger.warning(
                "All agents have zero variance; using equal weights"
            )
            w_arr = np.ones(n_agents) / n_agents
            return self._build_allocation(
                mat, w_arr, agent_names, method="equal_weight_fallback"
            )

        # Try optimization; fall back to equal weights on any failure
        try:
            w_arr = self._run_optimization(mat, agent_names)
            if w_arr is None:
                raise RuntimeError("Optimizer returned None")
            method_used = self.method
        except Exception:
            logger.warning(
                "Portfolio optimization failed, falling back to equal weights",
                exc_info=True,
            )
            w_arr = np.ones(n_agents) / n_agents
            method_used = "equal_weight_fallback"

        return self._build_allocation(mat, w_arr, agent_names, method=method_used)

    # ------------------------------------------------------------------
    # Internal: optimization dispatch
    # ------------------------------------------------------------------

    def _run_optimization(
        self, returns_matrix: np.ndarray, agent_names: list[str]
    ) -> np.ndarray | None:
        """Run the selected optimization and return weight array."""
        df = pd.DataFrame(returns_matrix, columns=agent_names)
        port = rp.Portfolio(returns=df)
        port.assets_stats(method_mu="hist", method_cov="hist")

        # Set weight constraints for mean-variance / CVaR optimization
        port.upperlng = self.max_weight
        if self.min_weight > 0:
            port.lowerlng = self.min_weight

        if self.method == "risk_parity":
            w_df = port.rp_optimization(
                model="Classic",
                rm="CVaR",
                rf=self.risk_free_rate,
                hist=True,
            )
            if w_df is None:
                return None
            w_arr = w_df["weights"].values
            # rp_optimization doesn't respect upperlng/lowerlng,
            # so clip and renormalize
            w_arr = self._clip_and_renormalize(w_arr)
            return w_arr

        elif self.method == "min_cvar":
            w_df = port.optimization(
                model="Classic",
                rm="CVaR",
                obj="MinRisk",
                rf=self.risk_free_rate,
                hist=True,
            )
        elif self.method == "max_sharpe":
            w_df = port.optimization(
                model="Classic",
                rm="MV",
                obj="Sharpe",
                rf=self.risk_free_rate,
                hist=True,
            )
        else:
            return None

        if w_df is None:
            return None
        return w_df["weights"].values

    def _clip_and_renormalize(
        self, weights: np.ndarray, max_iters: int = 50
    ) -> np.ndarray:
        """Clip weights to [min_weight, max_weight] and renormalize to sum=1.

        Uses iterative redistribution: clip the over-limit weights, then
        redistribute the excess proportionally among uncapped weights.
        """
        w = weights.copy()
        for _ in range(max_iters):
            capped = w > self.max_weight
            if not capped.any():
                break
            excess = (w[capped] - self.max_weight).sum()
            w[capped] = self.max_weight
            uncapped = ~capped
            if uncapped.any() and w[uncapped].sum() > 0:
                w[uncapped] += excess * (w[uncapped] / w[uncapped].sum())
            else:
                # All capped — distribute evenly
                w = np.ones_like(w) * self.max_weight
                break

        # Apply min weight
        if self.min_weight > 0:
            below = w < self.min_weight
            if below.any():
                w[below] = self.min_weight

        # Final renormalize
        total = w.sum()
        if total > 0:
            w = w / total
        else:
            w = np.ones_like(w) / len(w)
        return w

    # ------------------------------------------------------------------
    # Internal: build result
    # ------------------------------------------------------------------

    def _build_allocation(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        agent_names: list[str],
        method: str,
    ) -> PortfolioAllocation:
        """Construct a PortfolioAllocation from raw arrays."""
        port_returns = returns_matrix @ weights
        expected_return = float(port_returns.mean())
        expected_volatility = float(port_returns.std())
        cvar_95 = self._compute_cvar(returns_matrix, weights, alpha=0.05)
        div_ratio = self._compute_diversification_ratio(returns_matrix, weights)

        weight_dict = {
            name: float(w) for name, w in zip(agent_names, weights)
        }

        return PortfolioAllocation(
            weights=weight_dict,
            method=method,
            expected_return=expected_return,
            expected_volatility=expected_volatility,
            cvar_95=cvar_95,
            diversification_ratio=div_ratio,
        )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_returns_matrix(
        returns: dict[str, list[float]], agent_names: list[str]
    ) -> np.ndarray:
        """Convert dict of return lists to numpy matrix (T x N)."""
        columns = [np.array(returns[name], dtype=float) for name in agent_names]
        return np.column_stack(columns)

    @staticmethod
    def _compute_cvar(
        returns: np.ndarray, weights: np.ndarray, alpha: float = 0.05
    ) -> float:
        """Compute portfolio CVaR at given alpha level.

        CVaR (Conditional Value at Risk) is the expected loss in the worst
        alpha-fraction of scenarios.
        """
        portfolio_returns = returns @ weights
        sorted_returns = np.sort(portfolio_returns)
        cutoff = int(len(sorted_returns) * alpha)
        if cutoff == 0:
            cutoff = 1
        return float(-sorted_returns[:cutoff].mean())

    @staticmethod
    def _compute_diversification_ratio(
        returns: np.ndarray, weights: np.ndarray
    ) -> float:
        """Ratio of weighted individual vols to portfolio vol. >1 = diversified."""
        individual_vols = returns.std(axis=0)
        weighted_vols = float(np.sum(weights * individual_vols))
        portfolio_vol = float((returns @ weights).std())
        if portfolio_vol == 0:
            return 1.0
        return weighted_vols / portfolio_vol
