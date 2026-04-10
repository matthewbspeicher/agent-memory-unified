"""Risk Analytics Module — real-time risk metrics for trading positions.

Provides:
- Value at Risk (VaR) calculation
- Drawdown tracking
- Exposure limits by asset/class
- Leverage monitoring
- Margin utilization
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class RiskMetric(str, Enum):
    """Risk metrics tracked."""

    VAR_95 = "var_95"  # 95% VaR
    VAR_99 = "var_99"  # 99% VaR
    CVAR = "cvar"  # Conditional VaR (Expected Shortfall)
    MAX_DRAWDOWN = "max_drawdown"
    LEVERAGE = "leverage"
    EXPOSURE = "exposure"
    MARGIN_UTILIZATION = "margin_utilization"


@dataclass
class PositionRisk:
    """Risk metrics for a single position."""

    symbol: str
    quantity: Decimal
    avg_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

    # VaR metrics
    var_95: Decimal = Decimal("0")
    var_99: Decimal = Decimal("0")

    # Exposure
    long_exposure: Decimal = Decimal("0")
    short_exposure: Decimal = Decimal("0")
    net_exposure: Decimal = Decimal("0")


@dataclass
class PortfolioRisk:
    """Aggregated portfolio risk metrics."""

    timestamp: datetime

    # Position counts
    total_positions: int
    long_positions: int
    short_positions: int

    # Notional values
    total_long_notional: Decimal = Decimal("0")
    total_short_notional: Decimal = Decimal("0")
    net_notional: Decimal = Decimal("0")
    gross_notional: Decimal = Decimal("0")

    # VaR
    portfolio_var_95: Decimal = Decimal("0")
    portfolio_var_99: Decimal = Decimal("0")
    portfolio_cvar: Decimal = Decimal("0")

    # Drawdown
    current_drawdown: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    current_equity: Decimal = Decimal("0")

    # Leverage
    current_leverage: Decimal = Decimal("1")
    max_leverage: Decimal = Decimal("1")

    # Margin
    margin_used: Decimal = Decimal("0")
    margin_available: Decimal = Decimal("0")
    margin_utilization: Decimal = Decimal("0")

    # Per-position risks
    position_risks: list[PositionRisk] = field(default_factory=list)


@dataclass
class RiskLimit:
    """Configurable risk limits."""

    # VaR limits
    max_var_95_pct: float = 0.02  # 2% of portfolio
    max_var_99_pct: float = 0.04  # 4% of portfolio

    # Drawdown limits
    max_drawdown_pct: float = 0.10  # 10%
    daily_loss_limit_pct: float = 0.05  # 5% daily

    # Exposure limits
    max_net_exposure_pct: float = 1.0  # 100% of portfolio
    max_gross_exposure_pct: float = 2.0  # 200% of portfolio
    max_single_position_pct: float = 0.15  # 15%

    # Leverage
    max_leverage: float = 2.0

    # Margin
    max_margin_utilization: float = 0.80  # 80%


@dataclass
class RiskViolation:
    """A risk limit that was breached."""

    limit_name: str
    current_value: float
    limit_value: float
    severity: str  # "warning", "critical"
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RiskAnalytics:
    """
    Real-time risk analytics for trading positions.

    Calculates:
    - Value at Risk (VaR) using historical simulation
    - Drawdown tracking
    - Position-level and portfolio exposure
    - Leverage monitoring
    - Margin utilization
    """

    def __init__(
        self,
        limits: RiskLimit | None = None,
        lookback_days: int = 30,
        initial_equity: Decimal | None = None,
    ) -> None:
        self._limits = limits or RiskLimit()
        self._lookback_days = lookback_days

        # Equity history for drawdown
        self._equity_history: list[tuple[datetime, Decimal]] = []
        self._peak_equity: Decimal = initial_equity or Decimal("100000")

        # Daily P&L for VaR
        self._daily_pnl_history: list[float] = []

    def calculate_var(
        self,
        returns: list[float],
        confidence: float = 0.95,
    ) -> float:
        """Calculate Value at Risk using historical simulation.

        Args:
            returns: List of historical returns (e.g., [-0.02, 0.01, -0.005])
            confidence: Confidence level (0.95 or 0.99)

        Returns:
            VaR as a positive number (e.g., 0.02 = 2%)
        """
        if not returns or len(returns) < 10:
            return 0.0

        # Use percentile based on (1 - confidence)
        # For 95% VaR, we want the 5th percentile
        # For 99% VaR, we want the 1st percentile
        percentile = (1 - confidence) * 100
        raw_var = float(np.percentile(returns, percentile))
        # VaR represents potential loss — if the quantile is negative, the loss is its magnitude
        # If the quantile is positive (all-positive returns), VaR is effectively zero
        return max(0.0, -raw_var)

    def calculate_cvar(
        self,
        returns: list[float],
        confidence: float = 0.95,
    ) -> float:
        """Calculate Conditional VaR (Expected Shortfall).

        Average of all returns below the VaR threshold.
        """
        if not returns or len(returns) < 10:
            return 0.0

        var = self.calculate_var(returns, confidence)
        tail_returns = [r for r in returns if r <= -var]

        if not tail_returns:
            return var

        return float(abs(np.mean(tail_returns)))

    def update_equity(self, equity: Decimal) -> None:
        """Update equity for drawdown tracking."""
        now = datetime.now(timezone.utc)
        self._equity_history.append((now, equity))

        # Update peak
        if equity > self._peak_equity:
            self._peak_equity = equity

        # Keep only last 90 days
        cutoff = now.timestamp() - (90 * 24 * 3600)
        self._equity_history = [
            (ts, eq) for ts, eq in self._equity_history if ts.timestamp() > cutoff
        ]

    def calculate_drawdown(self) -> tuple[float, float]:
        """Calculate current and max drawdown.

        Returns:
            (current_drawdown_pct, max_drawdown_pct)
        """
        if not self._equity_history or self._peak_equity == 0:
            return 0.0, 0.0

        current_equity = self._equity_history[-1][1]

        # Current drawdown
        current_dd = float((self._peak_equity - current_equity) / self._peak_equity)

        # Max drawdown - track running peak at each point in time
        max_dd = 0.0
        running_peak = Decimal("0")
        for _, eq in self._equity_history:
            if eq > running_peak:
                running_peak = eq
            if running_peak > 0:
                dd = float((running_peak - eq) / running_peak)
                if dd > max_dd:
                    max_dd = dd

        return current_dd, max_dd

    def calculate_portfolio_risk(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, Decimal],
    ) -> PortfolioRisk:
        """Calculate aggregated portfolio risk metrics.

        Args:
            positions: List of position dicts with keys: symbol, quantity, avg_price
            prices: Current prices by symbol

        Returns:
            PortfolioRisk with all calculated metrics
        """
        now = datetime.now(timezone.utc)

        position_risks: list[PositionRisk] = []
        total_long = Decimal("0")
        total_short = Decimal("0")

        for pos in positions:
            symbol = pos["symbol"]
            qty = Decimal(str(pos.get("quantity", 0)))
            avg_price = Decimal(str(pos.get("avg_price", 0)))
            current_price = prices.get(symbol, avg_price)

            if qty == 0 or current_price == 0:
                continue

            market_value = abs(qty * current_price)
            unrealized = (current_price - avg_price) * qty

            # Long/short classification
            if qty > 0:
                total_long += market_value
                net_exp = market_value
            else:
                total_short += market_value
                net_exp = -market_value

            pos_risk = PositionRisk(
                symbol=symbol,
                quantity=qty,
                avg_price=avg_price,
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized,
                long_exposure=market_value if qty > 0 else Decimal("0"),
                short_exposure=market_value if qty < 0 else Decimal("0"),
                net_exposure=net_exp,
            )
            position_risks.append(pos_risk)

        # Calculate aggregates
        gross = total_long + total_short
        net = total_long - total_short

        # Current equity (simplified - would come from broker)
        current_equity = self._peak_equity
        if position_risks:
            # Add unrealized P&L
            total_unrealized = sum(p.unrealized_pnl for p in position_risks)
            current_equity += total_unrealized

        # Update equity tracking
        if current_equity > 0:
            self.update_equity(current_equity)

        # Drawdown
        current_dd, max_dd = self.calculate_drawdown()

        # Calculate VaR from daily P&L history
        if len(self._daily_pnl_history) >= 30:
            returns = self._daily_pnl_history
            var_95 = Decimal(str(self.calculate_var(returns, 0.95)))
            var_99 = Decimal(str(self.calculate_var(returns, 0.99)))
            cvar = Decimal(str(self.calculate_cvar(returns, 0.95)))
        else:
            var_95 = var_99 = cvar = Decimal("0")

        # Leverage
        if current_equity > 0:
            leverage = gross / current_equity
        else:
            leverage = Decimal("1")

        return PortfolioRisk(
            timestamp=now,
            total_positions=len(position_risks),
            long_positions=sum(1 for p in position_risks if p.quantity > 0),
            short_positions=sum(1 for p in position_risks if p.quantity < 0),
            total_long_notional=total_long,
            total_short_notional=total_short,
            net_notional=net,
            gross_notional=gross,
            portfolio_var_95=var_95,
            portfolio_var_99=var_99,
            portfolio_cvar=cvar,
            current_drawdown=Decimal(str(current_dd)),
            max_drawdown=Decimal(str(max_dd)),
            peak_equity=self._peak_equity,
            current_equity=current_equity,
            current_leverage=leverage,
            max_leverage=leverage,  # Simplified
            position_risks=position_risks,
        )

    def check_limits(self, risk: PortfolioRisk) -> list[RiskViolation]:
        """Check current risk against configured limits.

        Args:
            risk: Calculated portfolio risk

        Returns:
            List of violations (empty if all OK)
        """
        violations: list[RiskViolation] = []

        # VaR checks
        equity = float(risk.current_equity) if risk.current_equity > 0 else 1.0
        var_95_pct = float(risk.portfolio_var_95) / equity

        if var_95_pct > self._limits.max_var_95_pct:
            violations.append(
                RiskViolation(
                    limit_name="max_var_95_pct",
                    current_value=var_95_pct,
                    limit_value=self._limits.max_var_95_pct,
                    severity="critical"
                    if var_95_pct > self._limits.max_var_95_pct * 1.5
                    else "warning",
                    message=f"95% VaR {var_95_pct:.2%} exceeds limit {self._limits.max_var_95_pct:.2%}",
                )
            )

        # Drawdown check
        if float(risk.current_drawdown) > self._limits.max_drawdown_pct:
            violations.append(
                RiskViolation(
                    limit_name="max_drawdown_pct",
                    current_value=float(risk.current_drawdown),
                    limit_value=self._limits.max_drawdown_pct,
                    severity="critical",
                    message=f"Drawdown {float(risk.current_drawdown):.2%} exceeds limit {self._limits.max_drawdown_pct:.2%}",
                )
            )

        # Exposure checks
        net_exp_pct = float(risk.net_notional) / equity if equity > 0 else 0
        gross_exp_pct = float(risk.gross_notional) / equity if equity > 0 else 0

        if abs(net_exp_pct) > self._limits.max_net_exposure_pct:
            violations.append(
                RiskViolation(
                    limit_name="max_net_exposure_pct",
                    current_value=abs(net_exp_pct),
                    limit_value=self._limits.max_net_exposure_pct,
                    severity="warning",
                    message=f"Net exposure {abs(net_exp_pct):.2%} exceeds limit {self._limits.max_net_exposure_pct:.2%}",
                )
            )

        if gross_exp_pct > self._limits.max_gross_exposure_pct:
            violations.append(
                RiskViolation(
                    limit_name="max_gross_exposure_pct",
                    current_value=gross_exp_pct,
                    limit_value=self._limits.max_gross_exposure_pct,
                    severity="critical",
                    message=f"Gross exposure {gross_exp_pct:.2%} exceeds limit {self._limits.max_gross_exposure_pct:.2%}",
                )
            )

        # Leverage check
        if float(risk.current_leverage) > self._limits.max_leverage:
            violations.append(
                RiskViolation(
                    limit_name="max_leverage",
                    current_value=float(risk.current_leverage),
                    limit_value=self._limits.max_leverage,
                    severity="critical",
                    message=f"Leverage {float(risk.current_leverage):.2f}x exceeds limit {self._limits.max_leverage:.2f}x",
                )
            )

        return violations

    def record_daily_pnl(self, pnl: Decimal) -> None:
        """Record daily P&L for VaR calculation.

        Args:
            pnl: Daily profit/loss as Decimal
        """
        self._daily_pnl_history.append(float(pnl))

        # Keep last 252 days (1 year)
        if len(self._daily_pnl_history) > 252:
            self._daily_pnl_history = self._daily_pnl_history[-252:]
