from __future__ import annotations

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SimilarityFilter:
    """Aggregates outcomes of similar historical market states."""

    def __init__(self, min_neighbors: int = 2):
        self.min_neighbors = min_neighbors

    def process_neighbors(self, neighbors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze past outcomes of similar contexts."""
        if len(neighbors) < self.min_neighbors:
            return {"confidence_adjustment": 0.0, "reasoning": "Insufficient historical context."}

        outcomes = []
        for n in neighbors:
            metadata = n.get("metadata", {})
            metrics = metadata.get("metrics", {})
            
            # Look for PnL or outcome tags
            pnl = metrics.get("pnl")
            outcome = metrics.get("outcome")
            
            if pnl is not None:
                outcomes.append(float(pnl))
            elif outcome == "win":
                outcomes.append(0.01) # Proxy for win
            elif outcome == "loss":
                outcomes.append(-0.01) # Proxy for loss

        if not outcomes:
            return {"confidence_adjustment": 0.0, "reasoning": "Neighbors have no outcome data."}

        avg_pnl = sum(outcomes) / len(outcomes)
        win_rate = sum(1 for o in outcomes if o > 0) / len(outcomes)
        
        # Simple adjustment: boost if win rate > 60%, penalize if < 40%
        adjustment = 0.0
        if win_rate > 0.6:
            adjustment = 0.1
        elif win_rate < 0.4:
            adjustment = -0.1
            
        return {
            "confidence_adjustment": adjustment,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "neighbor_count": len(neighbors),
            "reasoning": f"Historical neighbors (n={len(neighbors)}) have {win_rate:.0%} win rate."
        }
