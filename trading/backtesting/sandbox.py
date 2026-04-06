"""BacktestSandbox — fast historical evaluation of agent configurations.

Used by Hermes to pre-screen agent configs before shadow deployment.
Combines ReplayDataBus (time-windowed DataBus) with the full metrics suite.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from agents.config import _STRATEGY_REGISTRY, _ensure_strategies_registered
from agents.models import AgentConfig, ActionLevel, TrustLevel
from broker.models import Bar, Symbol, AssetType
from data.backtest import HistoricalDataSource, ReplayDataBus
from data.bus import DataBus

logger = logging.getLogger(__name__)

# Sandbox guardrails
DEFAULT_TIMEOUT_SECONDS = 60
MAX_SYMBOLS = 50
MAX_PERIOD_BARS = 504  # ~2 years of daily bars


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of a sandbox evaluation. Contains everything Hermes needs to decide."""

    strategy: str
    parameters: dict[str, Any]
    symbols_tested: list[str]
    period: str

    # Core metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade_pnl: float = 0.0

    # Equity
    final_equity: Decimal = Decimal("0")
    initial_capital: Decimal = Decimal("100000")

    # Metadata
    evaluation_time_ms: int = 0
    error: str | None = None
    is_viable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "parameters": self.parameters,
            "symbols_tested": self.symbols_tested,
            "period": self.period,
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "total_return_pct": round(self.total_return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 4),
            "total_trades": self.total_trades,
            "avg_trade_pnl": round(self.avg_trade_pnl, 4),
            "final_equity": str(self.final_equity),
            "initial_capital": str(self.initial_capital),
            "evaluation_time_ms": self.evaluation_time_ms,
            "is_viable": self.is_viable,
            "error": self.error,
        }


class BacktestSandbox:
    """Fast historical evaluation of an agent config against cached market data.

    Usage:
        sandbox = BacktestSandbox(data_bus=live_bus)
        result = await sandbox.evaluate(
            strategy="rsi",
            parameters={"period": 14, "oversold": 25},
            symbols=["AAPL", "MSFT"],
            period="6mo",
        )
        if result.is_viable:
            # Shadow deploy this config
    """

    def __init__(
        self,
        data_bus: DataBus,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        min_sharpe: float = 0.3,
        min_trades: int = 5,
        max_drawdown: float = 25.0,
    ) -> None:
        self._data_bus = data_bus
        self._timeout = timeout_seconds
        self._min_sharpe = min_sharpe
        self._min_trades = min_trades
        self._max_drawdown = max_drawdown

    async def evaluate(
        self,
        strategy: str,
        parameters: dict[str, Any],
        symbols: list[str],
        *,
        universe: str | list[str] | None = None,
        period: str = "6mo",
        initial_capital: Decimal = Decimal("100000"),
    ) -> SandboxResult:
        """Evaluate an agent configuration against historical data.

        Args:
            strategy: Strategy name from _STRATEGY_REGISTRY (e.g. "rsi", "momentum").
            parameters: Strategy parameters (e.g. {"period": 14, "oversold": 30}).
            symbols: Tickers to backtest against.
            universe: Optional universe override for the agent config.
            period: Historical data period (e.g. "3mo", "6mo", "1y").
            initial_capital: Starting capital for the simulation.

        Returns:
            SandboxResult with metrics and viability assessment.
        """
        start_time = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self._run_evaluation(
                    strategy=strategy,
                    parameters=parameters,
                    symbols=symbols,
                    universe=universe,
                    period=period,
                    initial_capital=initial_capital,
                ),
                timeout=self._timeout,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            # Replace evaluation_time_ms (frozen dataclass, so reconstruct)
            return SandboxResult(
                **{
                    **{k: getattr(result, k) for k in result.__dataclass_fields__},
                    "evaluation_time_ms": elapsed_ms,
                }
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                "Sandbox evaluation timed out after %ds for strategy=%s",
                self._timeout,
                strategy,
            )
            return SandboxResult(
                strategy=strategy,
                parameters=parameters,
                symbols_tested=symbols,
                period=period,
                initial_capital=initial_capital,
                evaluation_time_ms=elapsed_ms,
                error=f"Evaluation timed out after {self._timeout}s",
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("Sandbox evaluation failed: %s", exc, exc_info=True)
            return SandboxResult(
                strategy=strategy,
                parameters=parameters,
                symbols_tested=symbols,
                period=period,
                initial_capital=initial_capital,
                evaluation_time_ms=elapsed_ms,
                error=str(exc),
            )

    async def _run_evaluation(
        self,
        strategy: str,
        parameters: dict[str, Any],
        symbols: list[str],
        universe: str | list[str] | None,
        period: str,
        initial_capital: Decimal,
    ) -> SandboxResult:
        # 1. Validate strategy exists
        _ensure_strategies_registered()
        if strategy not in _STRATEGY_REGISTRY:
            raise ValueError(
                f"Unknown strategy '{strategy}'. Available: {sorted(_STRATEGY_REGISTRY)}"
            )

        # 2. Guard against oversized requests
        if len(symbols) > MAX_SYMBOLS:
            symbols = symbols[:MAX_SYMBOLS]
            logger.warning("Truncated symbol list to %d for sandbox", MAX_SYMBOLS)

        # 3. Fetch historical data using the live DataBus
        sym_objects = [Symbol(ticker=t, asset_type=AssetType.STOCK) for t in symbols]
        bars_by_ticker: dict[str, list[Bar]] = {}

        for sym in sym_objects:
            try:
                bars = await self._data_bus.get_historical(
                    sym, timeframe="1d", period=period
                )
                if bars:
                    bars_by_ticker[sym.ticker] = sorted(
                        bars, key=lambda b: b.timestamp
                    )
            except Exception as exc:
                logger.warning(
                    "Sandbox: failed to fetch %s: %s", sym.ticker, exc
                )

        if not bars_by_ticker:
            raise ValueError("No historical data available for any requested symbol")

        # 4. Build the replay infrastructure
        hist_source = HistoricalDataSource(bars_by_ticker)
        replay_bus = ReplayDataBus(hist_source, starting_balance=initial_capital)

        # 5. Create a temporary agent instance
        agent_config = AgentConfig(
            name=f"sandbox_{strategy}",
            strategy=strategy,
            universe=universe or symbols,
            interval=60,
            schedule="on_demand",
            action_level=ActionLevel.NOTIFY,
            trust_level=TrustLevel.MONITORED,
            parameters=parameters,
        )
        factory = _STRATEGY_REGISTRY[strategy]
        agent = factory(agent_config)

        # 6. Collect all unique timestamps across all symbols
        all_times = sorted({
            b.timestamp
            for bars in bars_by_ticker.values()
            for b in bars
        })

        if not all_times:
            raise ValueError("No timestamps found in historical data")

        # Skip warmup period (first 20% of bars) to let indicators stabilize
        warmup = max(len(all_times) // 5, 50)
        tradeable_times = all_times[warmup:]

        if not tradeable_times:
            raise ValueError("Not enough data after warmup period")

        # 7. Run the simulation
        from data.backtest import BacktestEngine as ReplayEngine

        engine = ReplayEngine(bus=replay_bus, agents=[agent])
        raw = await engine.run(tradeable_times)

        # 8. Score the result
        from data.backtest import score_backtest_run

        scored = score_backtest_run(
            agent_name=f"sandbox_{strategy}",
            parameters=parameters,
            snapshots=raw["snapshots"],
            initial_equity=raw["initial_equity"],
            final_equity=raw["final_equity"],
        )

        # 9. Compute additional metrics from equity snapshots
        equities = [float(s["equity"]) for s in raw["snapshots"]]
        initial_eq = float(raw["initial_equity"])
        final_eq = float(raw["final_equity"])
        total_return_pct = ((final_eq - initial_eq) / initial_eq * 100) if initial_eq else 0.0

        # Sortino ratio (downside only)
        if len(equities) > 2:
            returns = [
                (equities[i] - equities[i - 1]) / equities[i - 1]
                for i in range(1, len(equities))
                if equities[i - 1] != 0
            ]
            downside = [r for r in returns if r < 0]
            if downside:
                import math
                avg_r = sum(returns) / len(returns)
                dd_var = sum(r**2 for r in downside) / len(returns)
                dd_dev = math.sqrt(dd_var) if dd_var > 0 else 0.0
                sortino = (avg_r / dd_dev * math.sqrt(252)) if dd_dev > 0 else 0.0
            else:
                sortino = float("inf") if total_return_pct > 0 else 0.0
        else:
            sortino = 0.0

        # Total executed trades
        total_trades = scored.total_trades

        # Average PnL per trade
        avg_pnl = (float(scored.total_pnl) / total_trades) if total_trades else 0.0

        # Viability check
        is_viable = (
            scored.sharpe_ratio >= self._min_sharpe
            and total_trades >= self._min_trades
            and scored.max_drawdown <= (self._max_drawdown / 100)
        )

        return SandboxResult(
            strategy=strategy,
            parameters=parameters,
            symbols_tested=list(bars_by_ticker.keys()),
            period=period,
            sharpe_ratio=scored.sharpe_ratio,
            sortino_ratio=sortino,
            total_return_pct=total_return_pct,
            max_drawdown_pct=scored.max_drawdown * 100,
            win_rate=scored.win_rate * 100,
            profit_factor=scored.profit_factor,
            total_trades=total_trades,
            avg_trade_pnl=avg_pnl,
            final_equity=Decimal(str(round(final_eq, 2))),
            initial_capital=initial_capital,
            is_viable=is_viable,
        )

    async def evaluate_variants(
        self,
        strategy: str,
        base_parameters: dict[str, Any],
        variants: list[dict[str, Any]],
        symbols: list[str],
        *,
        period: str = "6mo",
    ) -> list[SandboxResult]:
        """Evaluate multiple parameter variants and return results sorted by Sharpe.

        Used by Hermes to compare parameter explorations.
        """
        results = []
        for params in variants:
            merged = {**base_parameters, **params}
            result = await self.evaluate(
                strategy=strategy,
                parameters=merged,
                symbols=symbols,
                period=period,
            )
            results.append(result)

        # Sort by Sharpe descending, viable first
        results.sort(
            key=lambda r: (r.is_viable, r.sharpe_ratio),
            reverse=True,
        )
        return results
