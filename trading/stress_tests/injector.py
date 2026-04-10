"""StressTestInjector — runs agents against stress scenarios and records outcomes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from stress_tests.scenarios import StressScenario, ScenarioFactory, ScenarioType

logger = logging.getLogger(__name__)


@dataclass
class StressTestResult:
    """Result of running an agent through a stress scenario."""

    agent_name: str
    scenario_name: str
    scenario_type: ScenarioType
    severity: float
    baseline_sharpe: float
    stressed_sharpe: float
    sharpe_degradation: float
    max_drawdown: float
    num_trades: int
    passed: bool


class StressTestInjector:
    """Injects stress scenarios into agent backtests."""

    def __init__(
        self,
        sandbox: Any,
        degradation_threshold: float = 0.5,
    ):
        self._sandbox = sandbox
        self._threshold = degradation_threshold

    async def run_scenario(
        self,
        agent_name: str,
        strategy: str,
        parameters: dict[str, Any],
        symbols: list[str],
        scenario: StressScenario,
    ) -> StressTestResult:
        """Run agent through a single stress scenario."""
        baseline_result = await self._sandbox.run_backtest(
            strategy=strategy,
            parameters=parameters,
            symbols=symbols,
            period="3mo",
        )

        stressed_result = await self._sandbox.run_backtest(
            strategy=strategy,
            parameters=parameters,
            symbols=symbols,
            period="3mo",
            price_modifier=scenario.apply,
        )

        baseline_sharpe = baseline_result.sharpe_ratio or 0
        stressed_sharpe = stressed_result.sharpe_ratio or 0
        degradation = (
            (baseline_sharpe - stressed_sharpe) / abs(baseline_sharpe)
            if baseline_sharpe != 0
            else 0
        )

        return StressTestResult(
            agent_name=agent_name,
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type,
            severity=scenario.severity,
            baseline_sharpe=baseline_sharpe,
            stressed_sharpe=stressed_sharpe,
            sharpe_degradation=degradation,
            max_drawdown=stressed_result.max_drawdown or 0,
            num_trades=stressed_result.total_trades or 0,
            passed=degradation < self._threshold,
        )

    async def run_all_scenarios(
        self,
        agent_name: str,
        strategy: str,
        parameters: dict[str, Any],
        symbols: list[str],
        severities: list[float] | None = None,
    ) -> list[StressTestResult]:
        """Run agent through standard stress test suite."""
        if severities is None:
            severities = [0.3, 0.5, 0.7, 0.9]

        scenarios = []
        for sev in severities:
            scenarios.extend(
                [
                    ScenarioFactory.flash_crash(severity=sev, name=f"crash_s{sev}"),
                    ScenarioFactory.volatility_spike(severity=sev, name=f"vol_s{sev}"),
                    ScenarioFactory.gap_open(severity=sev, name=f"gap_s{sev}"),
                ]
            )

        results = []
        for scenario in scenarios:
            try:
                result = await self.run_scenario(
                    agent_name, strategy, parameters, symbols, scenario
                )
                results.append(result)
            except Exception as e:
                logger.warning(
                    "Stress test failed for %s/%s: %s", agent_name, scenario.name, e
                )

        return results
