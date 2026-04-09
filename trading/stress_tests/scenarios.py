"""Stress test scenarios for agent robustness evaluation.

Defines injectable market stress events: flash crashes, volatility spikes, gap opens.
Each scenario modifies price series to simulate extreme conditions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class ScenarioType(str, Enum):
    FLASH_CRASH = "flash_crash"
    VOLATILITY_SPIKE = "volatility_spike"
    GAP_OPEN = "gap_open"
    LIQUIDITY_DRAIN = "liquidity_drain"
    CORRELATION_BREAKDOWN = "correlation_breakdown"


@dataclass
class StressScenario:
    """Defines a stress test event to inject into price series."""

    name: str
    scenario_type: ScenarioType
    start_idx: int
    duration: int
    severity: float
    params: dict[str, Any] = field(default_factory=dict)

    def apply(self, prices: list[float]) -> list[float]:
        """Apply scenario to price series, returning modified copy."""
        result = prices.copy()

        if self.scenario_type == ScenarioType.FLASH_CRASH:
            return self._apply_flash_crash(result)
        elif self.scenario_type == ScenarioType.VOLATILITY_SPIKE:
            return self._apply_volatility_spike(result)
        elif self.scenario_type == ScenarioType.GAP_OPEN:
            return self._apply_gap_open(result)
        elif self.scenario_type == ScenarioType.LIQUIDITY_DRAIN:
            return self._apply_liquidity_drain(result)
        elif self.scenario_type == ScenarioType.CORRELATION_BREAKDOWN:
            return self._apply_correlation_breakdown(result)
        return result

    def _apply_flash_crash(self, prices: list[float]) -> list[float]:
        crash_pct = 0.05 + (self.severity * 0.25)
        recovery_pct = 0.3 + (self.severity * 0.3)

        end_idx = min(self.start_idx + self.duration, len(prices))
        crash_price = prices[self.start_idx] * (1 - crash_pct)
        recovery_target = (
            crash_price + (prices[self.start_idx] - crash_price) * recovery_pct
        )

        for i in range(self.start_idx, end_idx):
            progress = (i - self.start_idx) / (end_idx - self.start_idx)
            if progress < 0.2:
                prices[i] = crash_price * (1 + random.gauss(0, 0.01))
            else:
                recovery_progress = (progress - 0.2) / 0.8
                prices[i] = (
                    crash_price + (recovery_target - crash_price) * recovery_progress
                )
                prices[i] *= 1 + random.gauss(0, 0.005)

        return prices

    def _apply_volatility_spike(self, prices: list[float]) -> list[float]:
        vol_mult = 2.0 + (self.severity * 4.0)

        end_idx = min(self.start_idx + self.duration, len(prices))
        for i in range(self.start_idx, end_idx):
            if i > 0:
                normal_return = (prices[i] / prices[i - 1]) - 1
                spiked_return = normal_return * vol_mult + random.gauss(
                    0, 0.01 * self.severity
                )
                prices[i] = prices[i - 1] * (1 + spiked_return)

        return prices

    def _apply_volatility_spike(self, prices: list[float]) -> list[float]:
        """Extended period of high volatility."""
        vol_mult = 2.0 + (self.severity * 4.0)  # 2-6x normal volatility

        end_idx = min(self.start_idx + self.duration, len(prices))
        for i in range(self.start_idx, end_idx):
            if i > 0:
                normal_return = (prices[i] / prices[i - 1]) - 1
                spiked_return = normal_return * vol_mult + random.gauss(
                    0, 0.01 * self.severity
                )
                prices[i] = prices[i - 1] * (1 + spiked_return)

        return prices

    def _apply_gap_open(self, prices: list[float]) -> list[float]:
        gap_pct = (0.02 + self.severity * 0.08) * (1 if random.random() > 0.5 else -1)

        if self.start_idx < len(prices):
            prices[self.start_idx] *= 1 + gap_pct

        return prices

    def _apply_liquidity_drain(self, prices: list[float]) -> list[float]:
        spread_mult = 1.5 + (self.severity * 3.0)

        end_idx = min(self.start_idx + self.duration, len(prices))
        for i in range(self.start_idx, end_idx):
            noise = random.gauss(0, 0.005 * spread_mult)
            prices[i] *= 1 + noise

        return prices

    def _apply_correlation_breakdown(self, prices: list[float]) -> list[float]:
        end_idx = min(self.start_idx + self.duration, len(prices))
        for i in range(self.start_idx, end_idx):
            random_shock = random.gauss(0, 0.02 * self.severity)
            prices[i] *= 1 + random_shock

        return prices

    def _apply_liquidity_drain(self, prices: list[float]) -> list[float]:
        """Simulates thin order book - larger spreads, more slippage impact."""
        spread_mult = 1.5 + (self.severity * 3.0)

        end_idx = min(self.start_idx + self.duration, len(prices))
        for i in range(self.start_idx, end_idx):
            noise = random.gauss(0, 0.005 * spread_mult)
            prices[i] *= 1 + noise

        return prices

    def _apply_correlation_breakdown(self, prices: list[float]) -> list[float]:
        """Prices decouple from expected patterns - random walks dominate."""
        end_idx = min(self.start_idx + self.duration, len(prices))
        for i in range(self.start_idx, end_idx):
            random_shock = random.gauss(0, 0.02 * self.severity)
            prices[i] *= 1 + random_shock

        return prices


class ScenarioFactory:
    """Factory for creating common stress scenarios."""

    @staticmethod
    def flash_crash(
        severity: float = 0.5,
        start_idx: int = 100,
        duration: int = 20,
        name: str = "flash_crash",
    ) -> StressScenario:
        return StressScenario(
            name=name,
            scenario_type=ScenarioType.FLASH_CRASH,
            start_idx=start_idx,
            duration=duration,
            severity=severity,
        )

    @staticmethod
    def volatility_spike(
        severity: float = 0.5,
        start_idx: int = 100,
        duration: int = 50,
        name: str = "vol_spike",
    ) -> StressScenario:
        return StressScenario(
            name=name,
            scenario_type=ScenarioType.VOLATILITY_SPIKE,
            start_idx=start_idx,
            duration=duration,
            severity=severity,
        )

    @staticmethod
    def gap_open(
        severity: float = 0.5,
        start_idx: int = 100,
        name: str = "gap_open",
    ) -> StressScenario:
        return StressScenario(
            name=name,
            scenario_type=ScenarioType.GAP_OPEN,
            start_idx=start_idx,
            duration=1,
            severity=severity,
        )

    @staticmethod
    def crisis_scenario(
        start_idx: int = 100,
        name: str = "market_crisis",
    ) -> list[StressScenario]:
        """Full crisis sequence: gap down + volatility + crash + recovery."""
        return [
            StressScenario(f"{name}_gap", ScenarioType.GAP_OPEN, start_idx, 1, 0.7),
            StressScenario(
                f"{name}_vol", ScenarioType.VOLATILITY_SPIKE, start_idx, 30, 0.8
            ),
            StressScenario(
                f"{name}_crash", ScenarioType.FLASH_CRASH, start_idx + 5, 15, 0.9
            ),
        ]
