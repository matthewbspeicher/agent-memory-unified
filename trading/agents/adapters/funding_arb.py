# trading/agents/adapters/funding_arb.py
"""Funding rate arbitrage strategy — delta-neutral long spot / short perp."""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from data.sources.derivatives import FundingOISnapshot

logger = logging.getLogger(__name__)

# Annualized borrow rate estimates for shorting spot (as decimal, e.g. 0.03 = 3%)
BORROW_RATES = {
    "BTCUSD": 0.03,  # 3% annualized
    "ETHUSD": 0.05,  # 5% annualized
}
DEFAULT_BORROW_RATE = 0.05  # 5% annualized
# Base fee per funding period (0.04%), annualized
BASE_FEE_ANNUALIZED = 0.0004 * 3 * 365


@dataclass
class FundingArbConfig:
    min_annualized_rate: float = 0.20
    exit_rate: float = 0.05
    spike_threshold: float = 1.0
    spike_size_multiplier: float = 0.5
    allow_negative_funding: bool = False
    min_exchange_agreement: float = 0.80
    agreement_threshold: float = 0.10


@dataclass
class FundingArbSignal:
    direction: str  # "long_spot_short_perp" | "short_spot_long_perp" | "close"
    expected_annualized: float
    size_multiplier: float
    flags: list[str] = field(default_factory=list)
    confidence: float = 0.5


class FundingRateArbAdapter:
    """Evaluates funding rate arbitrage opportunities."""

    def __init__(self, config: FundingArbConfig | None = None):
        self.config = config or FundingArbConfig()

    def calculate_net_funding(self, annualized_rate: float, symbol: str) -> float:
        """Net return after fees and borrow costs."""
        if annualized_rate > 0:
            return annualized_rate - BASE_FEE_ANNUALIZED

        if not self.config.allow_negative_funding:
            return 0.0

        borrow = BORROW_RATES.get(symbol, DEFAULT_BORROW_RATE)
        net = abs(annualized_rate) - borrow - BASE_FEE_ANNUALIZED
        return max(net, 0.0)

    def check_exchange_agreement(self, snapshots: list[FundingOISnapshot]) -> bool:
        """Check if exchanges agree on funding rate direction and magnitude."""
        if len(snapshots) < 2:
            return False

        rates = [s.annualized_rate for s in snapshots]
        median_rate = statistics.median(rates)
        if abs(median_rate) < 0.01:
            return False

        agreeing = sum(
            1
            for r in rates
            if abs(r - median_rate) / max(abs(median_rate), 0.01)
            < self.config.agreement_threshold
        )
        return (agreeing / len(rates)) >= self.config.min_exchange_agreement

    def is_spike(self, annualized_rate: float) -> bool:
        return abs(annualized_rate) > self.config.spike_threshold

    def size_multiplier(self, annualized: float) -> float:
        if self.is_spike(annualized):
            return self.config.spike_size_multiplier
        return 1.0

    def evaluate(
        self,
        snapshots: list[FundingOISnapshot],
        symbol: str,
        has_position: bool = False,
    ) -> FundingArbSignal | None:
        """Evaluate funding snapshots and produce a signal."""
        if not self.check_exchange_agreement(snapshots):
            return None

        rates = [s.annualized_rate for s in snapshots]
        median_rate = statistics.median(rates)
        net = self.calculate_net_funding(median_rate, symbol)

        flags: list[str] = []
        if self.is_spike(median_rate):
            flags.append("spike_anomaly")

        # Entry signal
        if not has_position and net >= self.config.min_annualized_rate:
            direction = (
                "long_spot_short_perp" if median_rate > 0 else "short_spot_long_perp"
            )
            return FundingArbSignal(
                direction=direction,
                expected_annualized=net,
                size_multiplier=self.size_multiplier(median_rate),
                flags=flags,
                confidence=min(net / 0.5, 1.0),
            )

        # Exit signal
        if has_position and net < self.config.exit_rate:
            return FundingArbSignal(
                direction="close",
                expected_annualized=net,
                size_multiplier=1.0,
                flags=["exit_low_funding"],
                confidence=0.8,
            )

        return None
