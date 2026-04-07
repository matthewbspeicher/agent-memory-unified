from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timezone

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider

logger = logging.getLogger(__name__)


class RiskAuditProvider(BaseIntelProvider):
    """Monte Carlo VaR risk audit. Vetoes trades when tail risk is too high.

    Runs 10,000 GBM simulations to estimate 99% VaR. If the projected
    max loss exceeds the configured threshold, the trade is vetoed.
    """

    def __init__(self, var_threshold_pct: float = 5.0, horizon_days: int = 5):
        self.var_threshold_pct = var_threshold_pct
        self.horizon_days = horizon_days

    @property
    def name(self) -> str:
        return "risk_audit"

    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            price = await self._fetch_current_price(symbol)
            volatility = await self._fetch_volatility(symbol)
        except Exception as e:
            logger.warning("RiskAuditProvider failed for %s: %s", symbol, e)
            return None

        if price <= 0 or volatility <= 0:
            return None

        var_result = self._run_monte_carlo(price, volatility, self.horizon_days)

        var_99_pct = var_result["var_99_pct"]
        veto = var_99_pct > self.var_threshold_pct
        veto_reason = (
            f"99% VaR={var_99_pct:.1f}% exceeds {self.var_threshold_pct:.0f}% limit"
            if veto
            else None
        )

        # Score: negative when risk is high (bearish signal)
        # Normalized: 0 at threshold, -1 at 2x threshold
        score = 0.0
        if var_99_pct > self.var_threshold_pct:
            score = -min(
                (var_99_pct - self.var_threshold_pct) / self.var_threshold_pct, 1.0
            )

        return IntelReport(
            source=self.name,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            score=score,
            confidence=0.8,  # Monte Carlo is reliable given good vol inputs
            veto=veto,
            veto_reason=veto_reason,
            details=var_result,
        )

    async def _fetch_current_price(self, symbol: str) -> float:
        """Fetch current price. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

    async def _fetch_volatility(self, symbol: str) -> float:
        """Fetch annualized volatility. Override in tests."""
        raise NotImplementedError("Requires exchange API integration")

    @staticmethod
    def _run_monte_carlo(
        current_price: float,
        volatility: float,
        horizon_days: int,
        simulations: int = 10_000,
    ) -> dict:
        """GBM Monte Carlo with drift=0 (conservative/risk-neutral)."""
        dt = 1 / 252  # daily steps
        results = []

        for _ in range(simulations):
            price = current_price
            for _ in range(horizon_days):
                z = random.gauss(0, 1)
                change = math.exp(
                    -0.5 * (volatility**2) * dt + volatility * math.sqrt(dt) * z
                )
                price *= change
            results.append(price)

        results.sort()

        var_95 = current_price - results[int(simulations * 0.05)]
        var_99 = current_price - results[int(simulations * 0.01)]

        return {
            "current_price": current_price,
            "mean_end_price": round(sum(results) / simulations, 2),
            "var_95": round(var_95, 2),
            "var_99": round(var_99, 2),
            "var_95_pct": round((var_95 / current_price) * 100, 2),
            "var_99_pct": round((var_99 / current_price) * 100, 2),
            "horizon_days": horizon_days,
            "simulations": simulations,
        }
