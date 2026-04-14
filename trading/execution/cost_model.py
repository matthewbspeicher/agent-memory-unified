"""CostModel — calculates expected arbitrage profit after fees."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from broker.models import KalshiFeeModel, PolymarketFeeModel


@dataclass(frozen=True)
class ArbCostBreakdown:
    """Detailed breakdown of arbitrage costs and expected profit."""

    gross_gap_bps: Decimal
    kalshi_fee_bps: Decimal
    polymarket_fee_bps: Decimal
    total_fee_bps: Decimal
    net_profit_bps: Decimal
    is_profitable: bool


class CostModel:
    """Calculate expected arbitrage profit after accounting for exchange fees.

    For a cross-exchange arb (Kalshi ↔ Polymarket), both legs are taker orders,
    so we incur fees on both sides.

    Kalshi taker fee: 2% of notional
    Polymarket taker fee: 2% of notional
    Total round-trip fees: 4% of notional = 400 bps

    The gross gap is in cents (0-100 scale for prediction markets).
    We convert to bps: gap_cents * 100 (since 1 cent = 100 bps on 0-100 scale)
    """

    KALSHI_TAKER_RATE: Decimal = KalshiFeeModel.TAKER_FEE_RATE
    POLYMARKET_TAKER_RATE: Decimal = PolymarketFeeModel.TAKER_FEE_RATE

    @property
    def total_fee_rate(self) -> Decimal:
        """Combined taker fee rate for both exchanges."""
        return self.KALSHI_TAKER_RATE + self.POLYMARKET_TAKER_RATE

    @property
    def total_fee_bps(self) -> Decimal:
        """Combined fee in basis points."""
        return self.total_fee_rate * Decimal("10000")

    def expected_profit_bps(self, gap_cents: float | Decimal) -> Decimal:
        """Calculate expected net profit in basis points after fees.

        Args:
            gap_cents: Price gap in cents (e.g., 5.0 means 5 cent spread)

        Returns:
            Net profit in bps. Negative means the trade would lose money.
        """
        gap = Decimal(str(gap_cents))
        gross_bps = gap * Decimal("100")
        net_bps = gross_bps - self.total_fee_bps
        return net_bps

    def calculate_breakdown(
        self, gap_cents: float | Decimal, quantity: float | Decimal = 1.0
    ) -> ArbCostBreakdown:
        """Calculate detailed cost breakdown for an arbitrage opportunity.

        Args:
            gap_cents: Price gap in cents
            quantity: Number of contracts (used for notional calculation)

        Returns:
            ArbCostBreakdown with all cost details
        """
        gap = Decimal(str(gap_cents))
        qty = Decimal(str(quantity))

        gross_bps = gap * Decimal("100")
        kalshi_fee_bps = self.KALSHI_TAKER_RATE * Decimal("10000")
        poly_fee_bps = self.POLYMARKET_TAKER_RATE * Decimal("10000")
        total_fee = kalshi_fee_bps + poly_fee_bps
        net_bps = gross_bps - total_fee

        return ArbCostBreakdown(
            gross_gap_bps=gross_bps,
            kalshi_fee_bps=kalshi_fee_bps,
            polymarket_fee_bps=poly_fee_bps,
            total_fee_bps=total_fee,
            net_profit_bps=net_bps,
            is_profitable=net_bps > Decimal("0"),
        )

    def min_gap_cents(self) -> float:
        """Minimum gap required to break even (in cents)."""
        return float(self.total_fee_bps / Decimal("100"))

    def should_execute(
        self, gap_cents: float | Decimal, min_profit_bps: float = 0.0
    ) -> bool:
        """Determine if an arbitrage opportunity should be executed."""
        net = self.expected_profit_bps(gap_cents)
        return net > Decimal(str(min_profit_bps))
