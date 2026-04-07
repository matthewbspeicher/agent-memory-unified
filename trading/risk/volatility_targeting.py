"""Volatility targeting position sizing module.

Scales position sizes inversely to realized volatility so each position
contributes approximately equal risk to the portfolio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class VolatilityTarget:
    """Result of volatility-based position sizing."""

    raw_size: float  # original position size
    adjusted_size: float  # volatility-adjusted size
    realized_vol: float  # 20-day realized volatility (annualized)
    target_vol: float  # target volatility
    vol_scalar: float  # target_vol / realized_vol (clamped)
    regime: str | None  # current regime if available


class VolatilityTargeter:
    """Scales position sizes inversely to realized volatility.

    Formula: adjusted_size = raw_size * (target_vol / realized_vol)
    Clamped to [min_scalar, max_scalar] to prevent extreme sizing.

    In high-volatility regimes, positions shrink.
    In low-volatility regimes, positions grow (up to max_scalar).
    """

    def __init__(
        self,
        target_vol: float = 0.15,  # 15% annualized target vol
        lookback_days: int = 20,  # realized vol lookback
        min_scalar: float = 0.25,  # minimum 25% of raw size
        max_scalar: float = 2.0,  # maximum 200% of raw size
        annualize_factor: float = 365.0,  # crypto trades 365 days/year
    ):
        self.target_vol = target_vol
        self.lookback_days = lookback_days
        self.min_scalar = min_scalar
        self.max_scalar = max_scalar
        self.annualize_factor = annualize_factor

    def compute(
        self,
        returns: list[float],
        raw_size: float,
        regime: str | None = None,
    ) -> VolatilityTarget:
        """Compute volatility-adjusted position size.

        Args:
            returns: Recent daily returns (at least lookback_days).
            raw_size: Original position size from signal.
            regime: Optional regime label for logging.

        Returns:
            VolatilityTarget with adjusted_size.
        """
        n_available = len(returns)
        lookback = min(self.lookback_days, n_available)

        if lookback < 2:
            # Not enough data to compute volatility — pass through unchanged.
            return VolatilityTarget(
                raw_size=raw_size,
                adjusted_size=raw_size,
                realized_vol=0.0,
                target_vol=self.target_vol,
                vol_scalar=1.0,
                regime=regime,
            )

        realized_vol = self.realized_volatility(
            returns, lookback=lookback, annualize=self.annualize_factor
        )

        # Guard against zero / near-zero volatility (avoid division by zero).
        if realized_vol < 1e-12:
            return VolatilityTarget(
                raw_size=raw_size,
                adjusted_size=raw_size,
                realized_vol=0.0,
                target_vol=self.target_vol,
                vol_scalar=1.0,
                regime=regime,
            )

        vol_scalar = self.target_vol / realized_vol
        vol_scalar = max(self.min_scalar, min(self.max_scalar, vol_scalar))

        adjusted_size = raw_size * vol_scalar

        return VolatilityTarget(
            raw_size=raw_size,
            adjusted_size=adjusted_size,
            realized_vol=realized_vol,
            target_vol=self.target_vol,
            vol_scalar=vol_scalar,
            regime=regime,
        )

    @staticmethod
    def realized_volatility(
        returns: list[float],
        lookback: int = 20,
        annualize: float = 365.0,
    ) -> float:
        """Compute annualized realized volatility from daily returns.

        Uses the last ``lookback`` returns, computes the sample standard
        deviation, and multiplies by sqrt(annualize_factor).
        """
        window = returns[-lookback:]
        n = len(window)
        if n < 2:
            return 0.0

        mean = sum(window) / n
        variance = sum((r - mean) ** 2 for r in window) / (n - 1)
        daily_vol = math.sqrt(variance)
        return daily_vol * math.sqrt(annualize)
