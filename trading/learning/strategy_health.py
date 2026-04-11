"""StrategyHealthEngine — evaluates rolling live performance and manages health states.

Design notes:
- StrategyHealthStatus is SEPARATE from AgentStatus (RUNNING/STOPPED/ERROR).
  AgentStatus tracks operational lifecycle; StrategyHealthStatus tracks trading fitness.
- Tournament deconfliction: health state takes precedence over tournament stage for
  execution decisions. The tournament continues evaluating/recording independently.
  See: docs/superpowers/specs/2026-03-31-strategy-throttling-retirement-design.md
- SlippageFeedbackLoop deconfliction: the feedback loop should skip agents whose
  health state is throttled/shadow_only/retired (enforced in execution/feedback.py).
  For Phase 1, document only; the loop continues for normal/watchlist agents.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage.strategy_health import StrategyHealthStore
    from storage.performance import PerformanceStore

logger = logging.getLogger(__name__)


class StrategyHealthStatus(str, Enum):
    """Health states for a trading strategy.

    Separate from AgentStatus (RUNNING/STOPPED/ERROR) which tracks operational
    lifecycle. This enum tracks trading fitness.

    Transition path (degradation): normal → watchlist → throttled → shadow_only → retired
    Recovery path: watchlist/throttled → normal (when metrics improve)
    """

    NORMAL = "normal"
    WATCHLIST = "watchlist"
    THROTTLED = "throttled"
    SHADOW_ONLY = "shadow_only"
    RETIRED = "retired"


class StrategyHealthConfig:
    """Configuration for health evaluation thresholds."""

    def __init__(
        self,
        enabled: bool = True,
        default_window_trades: int = 50,
        default_expectancy_floor: float = 0.0,
        default_drawdown_limit: float = 5000.0,
        default_min_trade_count: int = 20,
        cooldown_hours: int = 24,
        recovery_window_trades: int = 30,
        throttle_multiplier: float = 0.5,
        retire_after_breaches: int = 3,
        max_consecutive_losses: int = 5,
        consecutive_loss_cooldown_hours: int = 48,
    ) -> None:
        self.enabled = enabled
        self.default_window_trades = default_window_trades
        self.default_expectancy_floor = default_expectancy_floor
        self.default_drawdown_limit = default_drawdown_limit
        self.default_min_trade_count = default_min_trade_count
        self.cooldown_hours = cooldown_hours
        self.recovery_window_trades = recovery_window_trades
        self.throttle_multiplier = throttle_multiplier
        self.retire_after_breaches = retire_after_breaches
        self.max_consecutive_losses = max_consecutive_losses
        self.consecutive_loss_cooldown_hours = consecutive_loss_cooldown_hours

    @classmethod
    def from_learning_config(cls, cfg: Any) -> "StrategyHealthConfig":
        """Build from a learning.yaml strategy_health sub-section (Pydantic or dict)."""
        if cfg is None:
            return cls()
        if isinstance(cfg, dict):
            return cls(
                **{
                    k: v
                    for k, v in cfg.items()
                    if k in cls.__init__.__code__.co_varnames
                }
            )
        return cls(
            enabled=getattr(cfg, "enabled", True),
            default_window_trades=getattr(cfg, "default_window_trades", 50),
            default_expectancy_floor=getattr(cfg, "default_expectancy_floor", 0.0),
            default_drawdown_limit=getattr(cfg, "default_drawdown_limit", 5000.0),
            default_min_trade_count=getattr(cfg, "default_min_trade_count", 20),
            cooldown_hours=getattr(cfg, "cooldown_hours", 24),
            recovery_window_trades=getattr(cfg, "recovery_window_trades", 30),
            throttle_multiplier=getattr(cfg, "throttle_multiplier", 0.5),
            retire_after_breaches=getattr(cfg, "retire_after_breaches", 3),
            max_consecutive_losses=getattr(cfg, "max_consecutive_losses", 5),
            consecutive_loss_cooldown_hours=getattr(
                cfg, "consecutive_loss_cooldown_hours", 48
            ),
        )


def _compute_expectancy(avg_win: float, avg_loss: float, win_rate: float) -> float:
    """Compute expectancy = win_rate * avg_win - (1 - win_rate) * abs(avg_loss)."""
    return win_rate * avg_win - (1.0 - win_rate) * abs(avg_loss)


class StrategyHealthEngine:
    """Evaluates rolling live performance and transitions strategies through health states.

    Phase 1 data source: PerformanceStore.get_latest() which already provides:
      win_rate, avg_win, avg_loss, max_drawdown, profit_factor, sharpe_ratio

    The engine is injected into OpportunityRouter as an optional dependency (same
    pattern as _regime_filter). It does NOT replace AgentStatus — it is a separate
    orthogonal dimension representing trading fitness.
    """

    def __init__(
        self,
        health_store: "StrategyHealthStore",
        perf_store: "PerformanceStore",
        config: StrategyHealthConfig | None = None,
    ) -> None:
        self._health_store = health_store
        self._perf_store = perf_store
        self._cfg = config or StrategyHealthConfig()

    async def get_status(self, agent_name: str) -> StrategyHealthStatus:
        """Return current health status for an agent, defaulting to NORMAL."""
        if not self._cfg.enabled:
            return StrategyHealthStatus.NORMAL
        row = await self._health_store.get_status(agent_name)
        if row is None:
            return StrategyHealthStatus.NORMAL
        # Manual override takes priority
        if row.get("manual_override"):
            return StrategyHealthStatus(row["status"])
        # Check cooldown — don't re-evaluate if still cooling down
        return StrategyHealthStatus(row["status"])

    async def get_throttle_multiplier(self, agent_name: str) -> float:
        """Return throttle multiplier for agent (1.0 if not throttled)."""
        row = await self._health_store.get_status(agent_name)
        if row and row.get("throttle_multiplier") is not None:
            return float(row["throttle_multiplier"])
        return self._cfg.throttle_multiplier

    async def evaluate(self, agent_name: str) -> StrategyHealthStatus:
        """Compute health state from PerformanceStore metrics and persist if changed.

        Returns the resulting StrategyHealthStatus.
        Fails open — any evaluation error returns NORMAL and logs a warning.
        """
        if not self._cfg.enabled:
            return StrategyHealthStatus.NORMAL

        try:
            return await self._evaluate_internal(agent_name)
        except Exception as exc:
            logger.warning(
                "StrategyHealthEngine.evaluate failed for %s (failing open): %s",
                agent_name,
                exc,
            )
            return StrategyHealthStatus.NORMAL

    async def _evaluate_internal(self, agent_name: str) -> StrategyHealthStatus:
        # Load latest performance snapshot
        snapshot = await self._perf_store.get_latest(agent_name)
        if snapshot is None:
            logger.debug(
                "No performance snapshot for %s — skipping health evaluation",
                agent_name,
            )
            return StrategyHealthStatus.NORMAL

        total_trades = snapshot.total_trades or 0
        if total_trades < self._cfg.default_min_trade_count:
            logger.debug(
                "Agent %s has %d trades < min %d — staying normal",
                agent_name,
                total_trades,
                self._cfg.default_min_trade_count,
            )
            return StrategyHealthStatus.NORMAL

        # Compute expectancy from available fields
        avg_win = float(snapshot.avg_win or 0)
        avg_loss = float(snapshot.avg_loss or 0)
        win_rate = float(snapshot.win_rate or 0)
        max_drawdown = float(snapshot.max_drawdown or 0)

        expectancy = _compute_expectancy(avg_win, avg_loss, win_rate)
        total_pnl = float(snapshot.total_pnl or 0)

        metrics = {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": expectancy,
            "max_drawdown": max_drawdown,
            "total_pnl": total_pnl,
            "profit_factor": float(snapshot.profit_factor or 0),
            "total_trades": total_trades,
        }

        consecutive_losses = snapshot.consecutive_losses or 0
        if consecutive_losses >= self._cfg.max_consecutive_losses:
            logger.warning(
                "Circuit breaker triggered for %s: %d consecutive losses >= %d",
                agent_name,
                consecutive_losses,
                self._cfg.max_consecutive_losses,
            )
            # Load current state for transition
            existing = await self._health_store.get_status(agent_name)
            current_status_str = (
                existing["status"] if existing else StrategyHealthStatus.NORMAL.value
            )
            current_status = StrategyHealthStatus(current_status_str)
            await self._transition(
                agent_name=agent_name,
                old_status=current_status,
                new_status=StrategyHealthStatus.THROTTLED,
                reason=f"Circuit breaker: {consecutive_losses} consecutive losses >= {self._cfg.max_consecutive_losses}",
                metrics=metrics,
            )
            return StrategyHealthStatus.THROTTLED

        # Load current state (for cooldown and transition logic)
        existing = await self._health_store.get_status(agent_name)
        current_status_str = (
            existing["status"] if existing else StrategyHealthStatus.NORMAL.value
        )
        current_status = StrategyHealthStatus(current_status_str)

        # Manual overrides are respected — do not auto-transition away from them
        if existing and existing.get("manual_override"):
            return current_status

        # Cooldown guard: don't transition again until cooldown expires
        if existing and existing.get("cooldown_until"):
            try:
                cooldown_until = datetime.fromisoformat(existing["cooldown_until"])
                if not cooldown_until.tzinfo:
                    cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < cooldown_until:
                    return current_status
            except (ValueError, TypeError):
                pass

        # Determine target status from metrics
        target_status = self._compute_target_status(
            current_status, expectancy, max_drawdown
        )

        if target_status != current_status:
            await self._transition(
                agent_name=agent_name,
                old_status=current_status,
                new_status=target_status,
                reason=self._build_reason(target_status, expectancy, max_drawdown),
                metrics=metrics,
            )

        return target_status

    def _compute_target_status(
        self,
        current: StrategyHealthStatus,
        expectancy: float,
        max_drawdown: float,
    ) -> StrategyHealthStatus:
        """Determine what status the agent SHOULD be in given current metrics."""
        expectancy_bad = expectancy < self._cfg.default_expectancy_floor
        drawdown_bad = max_drawdown > abs(
            self._cfg.default_drawdown_limit
        )  # drawdown stored as positive magnitude

        # Recovery: watchlist/throttled → normal when metrics improve
        if current in (StrategyHealthStatus.WATCHLIST, StrategyHealthStatus.THROTTLED):
            if not expectancy_bad and not drawdown_bad:
                return StrategyHealthStatus.NORMAL

        # Degradation transitions
        if current == StrategyHealthStatus.NORMAL and expectancy_bad:
            return StrategyHealthStatus.WATCHLIST

        if current == StrategyHealthStatus.WATCHLIST and (
            expectancy_bad or drawdown_bad
        ):
            return StrategyHealthStatus.THROTTLED

        if (
            current == StrategyHealthStatus.THROTTLED
            and expectancy_bad
            and drawdown_bad
        ):
            return StrategyHealthStatus.SHADOW_ONLY

        if (
            current == StrategyHealthStatus.SHADOW_ONLY
            and expectancy_bad
            and drawdown_bad
        ):
            return StrategyHealthStatus.RETIRED

        return current

    def _build_reason(
        self,
        target: StrategyHealthStatus,
        expectancy: float,
        max_drawdown: float,
    ) -> str:
        if target == StrategyHealthStatus.WATCHLIST:
            return f"Expectancy {expectancy:.4f} below floor {self._cfg.default_expectancy_floor}"
        if target == StrategyHealthStatus.THROTTLED:
            return (
                f"Persistent poor expectancy ({expectancy:.4f}) or drawdown "
                f"breach ({max_drawdown:.2f} > {abs(self._cfg.default_drawdown_limit)})"
            )
        if target == StrategyHealthStatus.SHADOW_ONLY:
            return f"Continued poor metrics despite throttling: expectancy={expectancy:.4f}"
        if target == StrategyHealthStatus.RETIRED:
            return f"Sustained underperformance: expectancy={expectancy:.4f}, drawdown={max_drawdown:.2f}"
        if target == StrategyHealthStatus.NORMAL:
            return f"Metrics recovered: expectancy={expectancy:.4f}"
        return "auto-evaluated"

    async def _transition(
        self,
        agent_name: str,
        old_status: StrategyHealthStatus,
        new_status: StrategyHealthStatus,
        reason: str,
        metrics: dict[str, Any],
    ) -> None:
        cooldown_until = (
            datetime.now(timezone.utc) + timedelta(hours=self._cfg.cooldown_hours)
        ).isoformat()

        throttle_multiplier: float | None = None
        if new_status == StrategyHealthStatus.THROTTLED:
            throttle_multiplier = self._cfg.throttle_multiplier

        await self._health_store.upsert_status(
            agent_name=agent_name,
            status=new_status.value,
            rolling_expectancy=str(metrics.get("expectancy", 0)),
            rolling_drawdown=str(metrics.get("max_drawdown", 0)),
            rolling_win_rate=metrics.get("win_rate"),
            rolling_trade_count=int(metrics.get("total_trades", 0)),
            throttle_multiplier=throttle_multiplier,
            trigger_reason=reason,
            cooldown_until=cooldown_until,
        )
        await self._health_store.record_event(
            agent_name=agent_name,
            old_status=old_status.value,
            new_status=new_status.value,
            reason=reason,
            metrics_snapshot=metrics,
            actor="system",
        )
        logger.info(
            "Strategy health transition: %s %s → %s (%s)",
            agent_name,
            old_status.value,
            new_status.value,
            reason,
        )

    async def on_trade_closed(self, agent_name: str) -> None:
        """Incremental recompute triggered after a trade closes.

        Called via asyncio.create_task() in the router's post-execution block
        (same pattern as trade_reflector). Reads from PerformanceStore.get_latest()
        which is already maintained by the mark-to-market scheduler.
        Safe to fail — logs warning on error.
        """
        try:
            await self.evaluate(agent_name)
        except Exception as exc:
            logger.warning(
                "StrategyHealthEngine.on_trade_closed failed for %s: %s",
                agent_name,
                exc,
            )

    async def recompute_all(self, agent_names: list[str]) -> dict[str, str]:
        """Admin: recompute health for all provided agent names.

        Returns mapping of agent_name → resulting status string.
        """

        # Use asyncio.gather for parallel execution
        async def eval_one(name: str) -> tuple[str, str]:
            status = await self.evaluate(name)
            return name, status.value

        results_list = await asyncio.gather(*[eval_one(name) for name in agent_names])
        return dict(results_list)
