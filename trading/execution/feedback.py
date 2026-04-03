"""SlippageFeedbackLoop — auto-downgrades agent trust when slippage eats edge."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from agents.models import TrustLevel

if TYPE_CHECKING:
    from execution.tracker import ExecutionFill, ExecutionTracker
    from storage.agent_registry import AgentStore
    from storage.performance import PerformanceStore

logger = logging.getLogger(__name__)


class SlippageFeedbackLoop:
    """Auto-downgrades agent trust when slippage consistently eats edge.

    On every ``check_agent`` call the loop:

    1. Fetches recent fills (within *max_days_lookback*).
    2. Computes average slippage in BPS.
    3. Computes edge in BPS from the latest performance snapshot.
    4. If slippage > edge for *consecutive_threshold* consecutive checks,
       downgrades the agent one trust level.
    5. If slippage <= edge and the agent was previously downgraded,
       upgrades the agent one trust level (up to its original ceiling).
    """

    TRUST_ORDER: list[TrustLevel] = [
        TrustLevel.MONITORED,
        TrustLevel.ASSISTED,
        TrustLevel.AUTONOMOUS,
    ]

    def __init__(
        self,
        tracker: ExecutionTracker,
        perf_store: PerformanceStore,
        agent_store: AgentStore,
        window: int = 20,
        consecutive_threshold: int = 3,
        min_fills: int = 10,
        max_days_lookback: int = 30,
    ) -> None:
        self._tracker = tracker
        self._perf_store = perf_store
        self._agent_store = agent_store
        self._window = window
        self._consecutive_threshold = consecutive_threshold
        self._min_fills = min_fills
        self._max_days_lookback = max_days_lookback
        # Per-agent consecutive breach counter
        self._consecutive_breach: dict[str, int] = {}
        # Ceiling for recovery — set the first time an agent is downgraded
        self._original_trust: dict[str, TrustLevel] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_agent(self, agent_name: str) -> tuple[str, TrustLevel] | None:
        """Evaluate slippage vs edge for *agent_name* and act if needed.

        Returns:
            ``("downgrade", new_trust)`` or ``("recovery", new_trust)`` when a
            trust change is made, otherwise ``None``.
        """
        fills = self._tracker.get_recent_fills(
            agent_name,
            limit=self._window,
            max_days=self._max_days_lookback,
        )
        if len(fills) < self._min_fills:
            return None

        avg_slippage_bps = sum(f.slippage_bps for f in fills) / len(fills)

        snapshot = await self._perf_store.get_latest(agent_name)
        if not snapshot or not snapshot.total_trades:
            return None

        avg_entry = self._compute_avg_entry(fills)
        if avg_entry == 0:
            return None

        avg_pnl = float(snapshot.total_pnl) / snapshot.total_trades
        edge_bps = abs(avg_pnl / avg_entry) * 10_000

        if avg_slippage_bps > edge_bps:
            self._consecutive_breach[agent_name] = (
                self._consecutive_breach.get(agent_name, 0) + 1
            )
            logger.debug(
                "Slippage (%.1f bps) > edge (%.1f bps) for %s — consecutive breach %d/%d",
                avg_slippage_bps,
                edge_bps,
                agent_name,
                self._consecutive_breach[agent_name],
                self._consecutive_threshold,
            )
            if self._consecutive_breach[agent_name] >= self._consecutive_threshold:
                self._consecutive_breach[agent_name] = 0
                return await self._downgrade(agent_name)
        else:
            if self._consecutive_breach.get(agent_name, 0) > 0:
                self._consecutive_breach[agent_name] = 0
                logger.debug(
                    "Slippage within edge for %s — breach counter reset", agent_name
                )
            return await self._try_recovery(agent_name)

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_avg_entry(fills: list[ExecutionFill]) -> float:
        """Return the mean expected (entry) price across fills."""
        if not fills:
            return 0.0
        return float(sum(f.expected_price for f in fills)) / len(fills)

    async def _get_current_trust(self, agent_name: str) -> TrustLevel:
        """Read the current trust level from the agent registry."""
        row = await self._agent_store.get(agent_name)
        if row and row.get("trust_level"):
            try:
                return TrustLevel(row["trust_level"])
            except ValueError:
                pass
        # Default to AUTONOMOUS if no override exists yet
        return TrustLevel.AUTONOMOUS

    async def _downgrade(self, agent_name: str) -> tuple[str, TrustLevel] | None:
        current = await self._get_current_trust(agent_name)
        # Record original trust ceiling the first time we downgrade
        if agent_name not in self._original_trust:
            self._original_trust[agent_name] = current
        idx = self.TRUST_ORDER.index(current) if current in self.TRUST_ORDER else 0
        if idx <= 0:
            logger.info(
                "Agent %s already at MONITORED — cannot downgrade further", agent_name
            )
            return None
        new_trust = self.TRUST_ORDER[idx - 1]
        await self._agent_store.update(agent_name, trust_level=new_trust.value)
        await self._agent_store.log_trust_change(
            agent_name, current.value, new_trust.value, "SlippageFeedbackLoop"
        )
        logger.warning(
            "SlippageFeedbackLoop: downgraded %s from %s → %s",
            agent_name,
            current.value,
            new_trust.value,
        )
        return ("downgrade", new_trust)

    async def _try_recovery(self, agent_name: str) -> tuple[str, TrustLevel] | None:
        if agent_name not in self._original_trust:
            return None  # Never been downgraded — nothing to recover
        current = await self._get_current_trust(agent_name)
        original = self._original_trust[agent_name]
        if current == original:
            return None  # Already at ceiling
        curr_idx = self.TRUST_ORDER.index(current) if current in self.TRUST_ORDER else 0
        orig_idx = self.TRUST_ORDER.index(original) if original in self.TRUST_ORDER else 0
        new_idx = min(curr_idx + 1, orig_idx)  # Don't exceed original trust ceiling
        new_trust = self.TRUST_ORDER[new_idx]
        if new_trust == current:
            return None  # No change
        await self._agent_store.update(agent_name, trust_level=new_trust.value)
        await self._agent_store.log_trust_change(
            agent_name, current.value, new_trust.value, "SlippageFeedbackLoop.recovery"
        )
        logger.info(
            "SlippageFeedbackLoop: recovered %s from %s → %s",
            agent_name,
            current.value,
            new_trust.value,
        )
        return ("recovery", new_trust)
