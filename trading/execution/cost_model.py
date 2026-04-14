"""CostModel — calculates expected arbitrage profit after fees and slippage."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from broker.models import KalshiFeeModel, PolymarketFeeModel

logger = logging.getLogger(__name__)


# Default slippage when no orderbook snapshot is available. Conservative —
# errs toward under-estimating profit so we don't green-light thin books.
# Sourced from recent Kalshi/Polymarket top-of-book depth analysis; revisit
# if we add orderbook capture to SpreadStore.
DEFAULT_SLIPPAGE_BPS = Decimal("15")


@dataclass(frozen=True)
class ArbCostBreakdown:
    """Detailed breakdown of arbitrage costs and expected profit."""

    gross_gap_bps: Decimal
    kalshi_fee_bps: Decimal
    polymarket_fee_bps: Decimal
    total_fee_bps: Decimal
    slippage_bps: Decimal
    net_profit_bps: Decimal
    is_profitable: bool
    slippage_is_estimated: bool


class CostModel:
    """Calculate expected arbitrage profit after accounting for exchange fees
    and a slippage estimate.

    For a Kalshi ↔ Polymarket arb, both legs are taker orders so we pay the
    taker fee on both sides. Gas costs are effectively zero for the current
    flow (Kalshi is centralized; Polymarket L2 settlement is batched by the
    exchange, not charged per-order to the taker).

    When an orderbook snapshot is unavailable (the common case against
    historical SpreadStore rows, which don't carry depth), we apply
    `DEFAULT_SLIPPAGE_BPS` and flag the estimate via
    `ArbCostBreakdown.slippage_is_estimated`.
    """

    KALSHI_TAKER_RATE: Decimal = KalshiFeeModel.TAKER_FEE_RATE
    POLYMARKET_TAKER_RATE: Decimal = PolymarketFeeModel.TAKER_FEE_RATE

    def __init__(self, default_slippage_bps: Decimal | None = None) -> None:
        self._default_slippage_bps = (
            default_slippage_bps
            if default_slippage_bps is not None
            else DEFAULT_SLIPPAGE_BPS
        )

    @property
    def total_fee_rate(self) -> Decimal:
        """Combined taker fee rate for both exchanges."""
        return self.KALSHI_TAKER_RATE + self.POLYMARKET_TAKER_RATE

    @property
    def total_fee_bps(self) -> Decimal:
        """Combined fee in basis points."""
        return self.total_fee_rate * Decimal("10000")

    def _resolve_slippage_bps(
        self, slippage_bps: Decimal | float | None
    ) -> tuple[Decimal, bool]:
        """Return (slippage_bps, is_estimated). Caller-provided slippage
        wins; otherwise we use the configured default and flag it."""
        if slippage_bps is None:
            return self._default_slippage_bps, True
        value = slippage_bps if isinstance(slippage_bps, Decimal) else Decimal(str(slippage_bps))
        return value, False

    def expected_profit_bps(
        self,
        gap_cents: float | Decimal,
        slippage_bps: Decimal | float | None = None,
    ) -> Decimal:
        """Net expected profit in bps after fees and slippage.

        Args:
            gap_cents: Price gap in cents (e.g., 5.0 means 5-cent spread).
            slippage_bps: Optional per-call slippage override. When omitted,
                falls back to the conservative default and logs a
                `cost_model.fallback` event.

        Returns:
            Net profit in bps. Negative = trade would lose money.
        """
        gap = Decimal(str(gap_cents))
        gross_bps = gap * Decimal("100")
        slippage, estimated = self._resolve_slippage_bps(slippage_bps)
        net_bps = gross_bps - self.total_fee_bps - slippage

        if estimated:
            logger.debug(
                "cost_model.fallback: orderbook snapshot absent; "
                "using default slippage %.1f bps",
                float(slippage),
                extra={
                    "event_type": "cost_model.fallback",
                    "data": {
                        "slippage_bps": float(slippage),
                        "gross_gap_bps": float(gross_bps),
                    },
                },
            )
        logger.debug(
            "cost_model.estimate: gap=%.1fc gross=%.0fbps fees=%.0fbps "
            "slip=%.0fbps net=%.0fbps",
            float(gap),
            float(gross_bps),
            float(self.total_fee_bps),
            float(slippage),
            float(net_bps),
            extra={
                "event_type": "cost_model.estimate",
                "data": {
                    "gap_cents": float(gap),
                    "gross_bps": float(gross_bps),
                    "fees_bps": float(self.total_fee_bps),
                    "slippage_bps": float(slippage),
                    "net_bps": float(net_bps),
                    "slippage_estimated": estimated,
                },
            },
        )
        return net_bps

    def calculate_breakdown(
        self,
        gap_cents: float | Decimal,
        quantity: float | Decimal = 1.0,
        slippage_bps: Decimal | float | None = None,
    ) -> ArbCostBreakdown:
        """Detailed cost breakdown for one arbitrage opportunity."""
        gap = Decimal(str(gap_cents))

        gross_bps = gap * Decimal("100")
        kalshi_fee_bps = self.KALSHI_TAKER_RATE * Decimal("10000")
        poly_fee_bps = self.POLYMARKET_TAKER_RATE * Decimal("10000")
        total_fee = kalshi_fee_bps + poly_fee_bps
        slippage, estimated = self._resolve_slippage_bps(slippage_bps)
        net_bps = gross_bps - total_fee - slippage

        return ArbCostBreakdown(
            gross_gap_bps=gross_bps,
            kalshi_fee_bps=kalshi_fee_bps,
            polymarket_fee_bps=poly_fee_bps,
            total_fee_bps=total_fee,
            slippage_bps=slippage,
            net_profit_bps=net_bps,
            is_profitable=net_bps > Decimal("0"),
            slippage_is_estimated=estimated,
        )

    def min_gap_cents(self, slippage_bps: Decimal | float | None = None) -> float:
        """Minimum gap in cents required to break even."""
        slippage, _ = self._resolve_slippage_bps(slippage_bps)
        return float((self.total_fee_bps + slippage) / Decimal("100"))

    def should_execute(
        self,
        gap_cents: float | Decimal,
        min_profit_bps: float = 0.0,
        slippage_bps: Decimal | float | None = None,
    ) -> bool:
        """Should we execute this opportunity at the given threshold?"""
        net = self.expected_profit_bps(gap_cents, slippage_bps=slippage_bps)
        return net > Decimal(str(min_profit_bps))
