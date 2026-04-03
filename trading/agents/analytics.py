import json
import logging
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from agents.base import Agent
from agents.models import Opportunity, AgentConfig
from agents.tuning import AdaptiveTuner
from storage.performance import PerformanceSnapshot

if TYPE_CHECKING:
    from agents.runner import AgentRunner
    from data.bus import DataBus
    from storage.opportunities import OpportunityStore
    from storage.performance import PerformanceStore
    from storage.trades import TradeStore

logger = logging.getLogger(__name__)


class AnalyticsAgent(Agent):
    """Periodically computes and stores performance analytics for all registered agents."""

    def __init__(
        self,
        config: AgentConfig | dict[str, Any],
        runner: 'AgentRunner | None' = None,
        opp_store: 'OpportunityStore | None' = None,
        perf_store: 'PerformanceStore | None' = None,
        trade_store: 'TradeStore | None' = None,
    ):
        super().__init__(config)
        self._runner = runner
        self._opp_store = opp_store
        self._perf_store = perf_store
        self._trade_store = trade_store

    @property
    def description(self) -> str:
        return "System agent tracking win rates and performance analytics."

    async def setup(self) -> None:
        pass

    async def teardown(self) -> None:
        pass

    def _compute_sharpe(self, pnl_values: list[float]) -> float:
        """Annualized Sharpe ratio from a sequence of per-trade P&L values."""
        if len(pnl_values) < 2:
            return 0.0
        n = len(pnl_values)
        mean = sum(pnl_values) / n
        variance = sum((x - mean) ** 2 for x in pnl_values) / (n - 1)
        std = math.sqrt(variance)
        if std == 0.0:
            return 0.0
        return (mean / std) * math.sqrt(252)

    def _compute_max_drawdown(self, pnl_values: list[float]) -> float:
        """Peak-to-trough max drawdown from cumulative equity curve."""
        if not pnl_values:
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnl_values:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        return max_dd

    async def _extract_trade_pnl(self, agent_name: str) -> list[float]:
        """Extract per-trade P&L from TradeStore for the given agent."""
        if not self._trade_store:
            return []
        trades = await self._trade_store.get_trades(agent_name=agent_name, limit=1000)
        pnl_values: list[float] = []
        for trade in trades:
            raw = trade.get("order_result")
            if not raw:
                continue
            try:
                result = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                continue
            avg_price = result.get("avg_fill_price")
            quantity = result.get("filled_quantity")
            side = result.get("side", "BUY")
            commission = float(result.get("commission", 0))
            if avg_price is None or quantity is None:
                continue
            gross = float(avg_price) * float(quantity)
            # BUY = cash outflow (negative P&L contribution), SELL = inflow
            if str(side).upper() == "SELL":
                pnl_values.append(gross - commission)
            else:
                pnl_values.append(-gross - commission)
        return pnl_values

    async def scan(self, data_bus: 'DataBus') -> list[Opportunity]:
        if not self._runner or not self._opp_store or not self._perf_store:
            logger.warning("AnalyticsAgent missing dependencies, skipping scan")
            return []

        tuner = AdaptiveTuner(self._runner, self._opp_store, self._trade_store)

        for agent_info in self._runner.list_agents():
            if agent_info.name == self.name:
                continue

            win_rate, _ = await tuner.get_agent_execution_rate(agent_info.name)
            opps = await self._opp_store.list(agent_name=agent_info.name, limit=1000)
            executed = sum(1 for o in opps if o["status"] == "executed")

            pnl_values = await self._extract_trade_pnl(agent_info.name)
            sharpe = self._compute_sharpe(pnl_values)
            max_dd = self._compute_max_drawdown(pnl_values)

            snapshot = PerformanceSnapshot(
                agent_name=agent_info.name,
                timestamp=datetime.now(timezone.utc),
                opportunities_generated=len(opps),
                opportunities_executed=executed,
                win_rate=win_rate,
                sharpe_ratio=sharpe,
                max_drawdown=max_dd,
            )
            await self._perf_store.save(snapshot)
            logger.info(
                "Saved performance snapshot for %s: win_rate=%.2f sharpe=%.4f max_dd=%.4f",
                agent_info.name, win_rate, sharpe, max_dd,
            )

        return []
