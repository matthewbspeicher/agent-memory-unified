"""Query service for market knowledge graph.

Provides high-level query operations for retrieving context bundles
and correlated symbols from the knowledge graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from knowledge.graph import MarketKnowledgeGraph
from knowledge.models import Entity, Relationship, RelationshipType, EntityType

import logging

logger = logging.getLogger(__name__)


@dataclass
class GraphContext:
    """Context bundle for a symbol at a point in time.

    Aggregates entity information, related entities, sector,
    recent events, and policy exposures for a given symbol.
    """

    symbol: str
    entity: Optional[Entity]
    related_entities: list[tuple[Entity, Relationship]] = field(default_factory=list)
    sector: Optional[Entity] = None
    recent_events: list[Entity] = field(default_factory=list)
    policy_exposures: list[tuple[Entity, Relationship]] = field(default_factory=list)


class GraphQueryService:
    """Query service for market knowledge graph.

    Provides high-level query operations that return structured
    context bundles for use by intelligence providers and agents.
    """

    def __init__(self, graph: MarketKnowledgeGraph) -> None:
        self._graph = graph

    def get_context_bundle(
        self,
        symbol: str,
        as_of: Optional[datetime] = None,
        max_depth: int = 2,
    ) -> GraphContext:
        """Get comprehensive context for a symbol.

        Args:
            symbol: Ticker symbol to query.
            as_of: Point in time for temporal queries (None = now).
            max_depth: Maximum relationship traversal depth.

        Returns:
            GraphContext with entity, relationships, and derived data.
        """
        as_of = as_of or datetime.now(timezone.utc)
        entity = self._graph.get_entity_by_symbol(symbol)

        if not entity:
            return GraphContext(
                symbol=symbol,
                entity=None,
                related_entities=[],
            )

        related = self._graph.get_related_entities(
            entity.id, max_depth=max_depth, as_of=as_of
        )

        sector = None
        recent_events: list[Entity] = []
        policy_exposures: list[tuple[Entity, Relationship]] = []

        event_cutoff = as_of - timedelta(days=7)

        for rel_entity, rel in related:
            if (
                rel.relationship_type == RelationshipType.BELONGS_TO_SECTOR
                and not sector
            ):
                sector = rel_entity

            if (
                rel_entity.entity_type == EntityType.EVENT
                and rel_entity.temporal.created_at > event_cutoff
            ):
                recent_events.append(rel_entity)

            if rel.relationship_type == RelationshipType.AFFECTED_BY_POLICY:
                policy_exposures.append((rel_entity, rel))

        return GraphContext(
            symbol=symbol,
            entity=entity,
            related_entities=related,
            sector=sector,
            recent_events=recent_events,
            policy_exposures=policy_exposures,
        )

    def get_correlated_symbols(
        self,
        symbol: str,
        min_strength: float = 0.5,
        as_of: Optional[datetime] = None,
    ) -> list[tuple[str, float]]:
        """Get symbols correlated with the given symbol.

        Args:
            symbol: Ticker symbol to query.
            min_strength: Minimum correlation strength (0.0-1.0).
            as_of: Point in time for temporal queries.

        Returns:
            List of (symbol, strength) tuples sorted by strength descending.
        """
        entity = self._graph.get_entity_by_symbol(symbol)
        if not entity:
            return []

        as_of = as_of or datetime.now(timezone.utc)
        related = self._graph.get_related_entities(
            entity.id,
            relationship_type=RelationshipType.CORRELATED_WITH,
            as_of=as_of,
        )

        results = []
        for rel_entity, rel in related:
            if rel_entity.symbol and rel.strength >= min_strength:
                results.append((rel_entity.symbol, rel.strength))

        return sorted(results, key=lambda x: x[1], reverse=True)

    def get_sector_exposure(
        self,
        sector_name: str,
        as_of: Optional[datetime] = None,
    ) -> list[Entity]:
        """Get all companies in a sector.

        Args:
            sector_name: Name of the sector.
            as_of: Point in time for temporal queries.

        Returns:
            List of company entities in the sector.
        """
        as_of = as_of or datetime.now(timezone.utc)

        sector_entities = self._graph.get_entities_by_type(EntityType.SECTOR)
        sector_entity = None
        for e in sector_entities:
            if e.name.lower() == sector_name.lower():
                sector_entity = e
                break

        if not sector_entity:
            return []

        incoming = self._graph.get_incoming_relationships(
            sector_entity.id,
            relationship_type=RelationshipType.BELONGS_TO_SECTOR,
            as_of=as_of,
        )

        return [
            entity for entity, _ in incoming if entity.entity_type == EntityType.COMPANY
        ]

    def get_policy_impact(
        self,
        policy_name: str,
        as_of: Optional[datetime] = None,
    ) -> list[tuple[Entity, Relationship]]:
        """Get entities affected by a policy.

        Args:
            policy_name: Name of the policy.
            as_of: Point in time for temporal queries.

        Returns:
            List of (affected_entity, relationship) tuples.
        """
        as_of = as_of or datetime.now(timezone.utc)

        policy_entities = self._graph.get_entities_by_type(EntityType.POLICY)
        policy_entity = None
        for e in policy_entities:
            if e.name.lower() == policy_name.lower():
                policy_entity = e
                break

        if not policy_entity:
            return []

        outgoing = self._graph.get_related_entities(
            policy_entity.id,
            relationship_type=RelationshipType.AFFECTS,
            as_of=as_of,
            max_depth=1,
        )

        return outgoing
