"""ExecutionAnalyzer — detects edge erosion from persistent slippage."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.tracker import ExecutionFill

logger = logging.getLogger(__name__)


class ExecutionAnalyzer:
    """
    Analyzes execution fills to detect edge erosion.

    Edge erosion occurs when slippage is consistently high enough to
    eat into the expected alpha from a strategy.
    """

    def __init__(self, erosion_threshold_bps: float = 50.0) -> None:
        """
        Args:
            erosion_threshold_bps: Average slippage above this (in bps)
                                   is considered edge-eroding.
        """
        self._threshold = erosion_threshold_bps

    def is_eroding_edge(self, agent_name: str, fills: list) -> bool:
        """Return True if average slippage exceeds the erosion threshold."""
        if not fills:
            return False
        avg = sum(f.slippage_bps for f in fills) / len(fills)
        eroding = avg > self._threshold
        if eroding:
            logger.warning(
                "Edge erosion detected for %s: avg slippage=%.1f bps (threshold=%.1f bps)",
                agent_name, avg, self._threshold,
            )
        return eroding

    def summary(self, agent_name: str, fills: list) -> dict:
        """Return a summary dict of execution quality for an agent."""
        if not fills:
            return {
                "agent_name": agent_name,
                "fill_count": 0,
                "avg_slippage_bps": 0.0,
                "max_slippage_bps": 0.0,
                "min_slippage_bps": 0.0,
                "edge_eroding": False,
            }

        slippages = [f.slippage_bps for f in fills]
        avg = sum(slippages) / len(slippages)

        return {
            "agent_name": agent_name,
            "fill_count": len(fills),
            "avg_slippage_bps": round(avg, 2),
            "max_slippage_bps": round(max(slippages), 2),
            "min_slippage_bps": round(min(slippages), 2),
            "edge_eroding": avg > self._threshold,
        }
