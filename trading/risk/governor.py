"""
CapitalGovernor — dynamic position sizing and portfolio correlation guard.

Integrates with LeaderboardEngine for Sharpe ratios and TournamentStore for stages.
Includes DrawdownWatchdog for persistent performance-based demotion.
"""
from __future__ import annotations

import logging
import time
import yaml
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Any

from risk.rules import RiskRule, RiskResult, PortfolioContext
from broker.models import OrderBase, Quote

if TYPE_CHECKING:
    from leaderboard.engine import LeaderboardEngine, AgentRanking
    from tournament.store import TournamentStore
    from storage.agent_registry import AgentStore
    from storage.performance import PerformanceStore
    from config import Config

logger = logging.getLogger(__name__)

@dataclass
class GovernorConfig:
    base_allocation_usd: float
    min_sharpe_for_promotion: float
    max_allocation_per_agent_usd: float
    scaling_factor: float
    max_drawdown_24h_pct: float
    demotion_threshold_sharpe: float
    max_correlation_threshold: float
    ttl_seconds: int

    @classmethod
    def load(cls, path: str = "governor.yaml") -> GovernorConfig:
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f)
            return cls(
                base_allocation_usd=data["capital_allocation"]["base_allocation_usd"],
                min_sharpe_for_promotion=data["capital_allocation"]["min_sharpe_for_promotion"],
                max_allocation_per_agent_usd=data["capital_allocation"]["max_allocation_per_agent_usd"],
                scaling_factor=data["capital_allocation"]["scaling_factor"],
                max_drawdown_24h_pct=data["circuit_breakers"]["max_drawdown_24h_pct"],
                demotion_threshold_sharpe=data["circuit_breakers"]["demotion_threshold_sharpe"],
                max_correlation_threshold=data["portfolio_risk"]["max_correlation_threshold"],
                ttl_seconds=data["cache"]["ttl_seconds"]
            )
        except Exception as e:
            logger.warning(f"Failed to load governor.yaml, using defaults: {e}")
            return cls(
                base_allocation_usd=100.0,
                min_sharpe_for_promotion=1.5,
                max_allocation_per_agent_usd=1000.0,
                scaling_factor=1.0,
                max_drawdown_24h_pct=5.0,
                demotion_threshold_sharpe=-1.0,
                max_correlation_threshold=0.7,
                ttl_seconds=300
            )

@dataclass
class GovernorCache:
    rankings: dict[str, AgentRanking]
    stages: dict[str, int]
    timestamp: float

class DrawdownWatchdog:
    """Monitors agent P&L and demotes trust levels on drawdown violation."""
    def __init__(
        self, 
        perf_store: PerformanceStore, 
        agent_store: AgentStore,
        config: GovernorConfig
    ):
        self._perf_store = perf_store
        self._agent_store = agent_store
        self._config = config

    async def check_all_agents(self, agent_names: list[str]):
        """Perform a sweep of all agents for drawdown violations."""
        for name in agent_names:
            snapshot = await self._perf_store.get_latest(name)
            if not snapshot:
                continue
            
            # Check 24h drawdown if available in snapshot
            # (Note: Requires performance_snapshots table to carry daily_pnl_pct)
            drawdown = getattr(snapshot, "daily_pnl_pct", 0.0)
            if drawdown is not None and abs(drawdown) > self._config.max_drawdown_24h_pct and drawdown < 0:
                await self.demote_agent(name, f"Drawdown {drawdown:.2f}% exceeded limit")

    async def demote_agent(self, agent_name: str, reason: str):
        """Persistently demote an agent to MONITORED status."""
        current = await self._agent_store.get(agent_name)
        old_level = current.get("trust_level", "UNKNOWN") if current else "AUTONOMOUS"
        
        if old_level == "MONITORED":
            return # Already demoted
            
        logger.warning(f"WATCHDOG: Demoting {agent_name} to MONITORED. Reason: {reason}")
        await self._agent_store.update(agent_name, trust_level="MONITORED")
        await self._agent_store.log_trust_change(
            agent_name, old_level, "MONITORED", "CapitalGovernor.Watchdog"
        )

class CapitalGovernor(RiskRule):
    name = "capital_governor"

    def __init__(
        self,
        leaderboard: LeaderboardEngine,
        tournament: TournamentStore,
        perf_store: PerformanceStore,
        agent_store: AgentStore,
        settings: Config,
        config_path: str = "governor.yaml"
    ) -> None:
        self._leaderboard = leaderboard
        self._tournament = tournament
        self._settings = settings
        self._gov_config = GovernorConfig.load(config_path)
        self._watchdog = DrawdownWatchdog(perf_store, agent_store, self._gov_config)
        self._cache: Optional[GovernorCache] = None

    async def _refresh_cache_if_needed(self) -> None:
        now = time.time()
        if (
            self._cache is None
            or (now - self._cache.timestamp) > self._gov_config.ttl_seconds
        ):
            rankings_list = await self._leaderboard.get_cached_leaderboard()
            if rankings_list is None:
                rankings_list = await self._leaderboard.compute_rankings()
            
            rankings_dict = {r.agent_name: r for r in rankings_list}
            stages_dict = await self._tournament.get_all_stages()
            
            self._cache = GovernorCache(
                rankings=rankings_dict,
                stages=stages_dict,
                timestamp=now
            )
            
            # Run periodic watchdog check
            await self._watchdog.check_all_agents(list(rankings_dict.keys()))

    async def evaluate(self, trade: OrderBase, quote: Quote, ctx: PortfolioContext) -> RiskResult:
        await self._refresh_cache_if_needed()

        agent_name = getattr(trade, "agent_name", "unknown")

        if not self._cache:
            return RiskResult(
                passed=True,
                rule_name=self.name,
                reason="Cache warming, defaulting to min size",
                adjusted_quantity=Decimal("1")
            )

        ranking = self._cache.rankings.get(agent_name)
        stage = self._cache.stages.get(agent_name, 0)

        # 1. Performance Demotion Check (via Sharpe)
        if ranking and ranking.sharpe_ratio < self._gov_config.demotion_threshold_sharpe:
            await self._watchdog.demote_agent(
                agent_name, f"Sharpe {ranking.sharpe_ratio:.2f} below threshold"
            )
            return RiskResult(
                passed=False,
                rule_name=self.name,
                reason=f"Agent {agent_name} demoted: Sharpe {ranking.sharpe_ratio:.2f} below threshold"
            )

        # 2. Dynamic Sizing Logic
        sharpe_ratio = ranking.sharpe_ratio if ranking else 0.0
        sharpe_mult = max(0.1, sharpe_ratio / self._gov_config.min_sharpe_for_promotion)
        stage_mult = max(0.1, stage / 3.0)
        
        size_factor = float(Decimal(str(sharpe_mult * stage_mult * self._gov_config.scaling_factor)))
        size_factor = max(0.1, min(1.0, size_factor))

        adjusted_qty = Decimal(str(round(float(trade.quantity) * size_factor)))
        if adjusted_qty < 1:
            adjusted_qty = Decimal("1")

        # 3. Correlation Guard
        if ctx.price_histories and trade.symbol.ticker in ctx.price_histories:
            new_prices = ctx.price_histories[trade.symbol.ticker]
            max_correlation = 0.0
            from risk.correlation import pearson_correlation
            
            for ticker, history in ctx.price_histories.items():
                if ticker == trade.symbol.ticker:
                    continue
                if any(p.symbol.ticker == ticker for p in ctx.positions):
                    correlation = pearson_correlation(new_prices, history)
                    max_correlation = max(max_correlation, correlation)
            
            if max_correlation > self._gov_config.max_correlation_threshold:
                old_qty = adjusted_qty
                adjusted_qty = Decimal(str(round(float(adjusted_qty) * 0.5)))
                if adjusted_qty < 1:
                    adjusted_qty = Decimal("1")
                
                logger.warning(
                    f"Governor: High correlation ({max_correlation:.2f}) for {trade.symbol.ticker}. "
                    f"Size reduced: {old_qty} -> {adjusted_qty}"
                )

        return RiskResult(
            passed=True,
            rule_name=self.name,
            adjusted_quantity=adjusted_qty
        )
