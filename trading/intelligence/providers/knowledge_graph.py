"""Knowledge graph intelligence provider.

Enriches trading signals with market entity relationships
and temporal context from the knowledge graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from intelligence.models import IntelReport
from intelligence.providers.base import BaseIntelProvider
from knowledge.query import GraphContext, GraphQueryService

import logging

logger = logging.getLogger(__name__)


class KnowledgeGraphProvider(BaseIntelProvider):
    """Intelligence provider that enriches signals with knowledge graph context.

    Analyzes market entities and their relationships to provide
    contextual intelligence for trading decisions.
    """

    def __init__(self, query_service: Optional[GraphQueryService] = None) -> None:
        self._query_service = query_service

    @property
    def name(self) -> str:
        return "knowledge_graph"

    async def analyze(self, symbol: str) -> Optional[IntelReport]:
        """Analyze symbol using knowledge graph context.

        Args:
            symbol: Trading symbol to analyze.

        Returns:
            IntelReport with graph-derived intelligence, or None if unavailable.
        """
        if not self._query_service:
            logger.debug("KnowledgeGraphProvider: No query service configured")
            return None

        try:
            context = self._query_service.get_context_bundle(symbol)

            if not context.entity:
                logger.debug("No graph entity for %s", symbol)
                return None

            score = self._compute_context_score(context)
            confidence = self._compute_confidence(context)

            return IntelReport(
                source=self.name,
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                score=score,
                confidence=confidence,
                veto=False,
                veto_reason=None,
                details={
                    "entity_name": context.entity.name,
                    "entity_type": context.entity.entity_type.value,
                    "sector": context.sector.name if context.sector else None,
                    "related_count": len(context.related_entities),
                    "recent_events": len(context.recent_events),
                    "policy_exposures": len(context.policy_exposures),
                },
            )
        except Exception as e:
            logger.warning("KnowledgeGraphProvider failed for %s: %s", symbol, e)
            return None

    def _compute_context_score(self, context: GraphContext) -> float:
        """Compute sentiment score from graph context.

        Aggregates signals from recent events and policy exposures
        to produce a score between -1.0 and +1.0.
        """
        score = 0.0

        for event in context.recent_events:
            event_sentiment = event.metadata.get("sentiment", 0.0)
            score += event_sentiment * 0.1

        for policy_entity, rel in context.policy_exposures:
            policy_impact = policy_entity.metadata.get("impact_score", 0.0)
            score += policy_impact * rel.strength * 0.15

        return max(-1.0, min(1.0, score))

    def _compute_confidence(self, context: GraphContext) -> float:
        """Compute confidence based on graph completeness.

        Higher confidence when more relationships and context available.
        """
        base_confidence = 0.5

        rel_count = len(context.related_entities)
        if rel_count > 10:
            base_confidence += 0.2
        elif rel_count > 5:
            base_confidence += 0.1

        if context.sector:
            base_confidence += 0.1

        if context.recent_events:
            base_confidence += 0.1

        return min(1.0, base_confidence)
