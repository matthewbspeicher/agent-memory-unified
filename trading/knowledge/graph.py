"""Market knowledge graph with temporal metadata tracking.

NetworkX-based directed graph for storing market entities and their
relationships with temporal validity windows.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Optional

import networkx as nx

from knowledge.models import (
    Entity,
    EntityType,
    Relationship,
    RelationshipType,
    TemporalMetadata,
)

import logging

logger = logging.getLogger(__name__)


class MarketKnowledgeGraph:
    """NetworkX-based knowledge graph with temporal metadata.

    Stores market entities (companies, sectors, indicators, etc.) and
    their relationships with temporal validity tracking. Supports
    querying by symbol, type, and relationship patterns.
    """

    def __init__(self) -> None:
        self._graph = nx.DiGraph()
        self._entity_index: dict[str, Entity] = {}
        self._symbol_index: dict[str, str] = {}  # symbol -> entity_id
        self._type_index: dict[EntityType, set[str]] = {t: set() for t in EntityType}

    @property
    def entity_count(self) -> int:
        """Total number of entities in the graph."""
        return len(self._entity_index)

    @property
    def relationship_count(self) -> int:
        """Total number of relationships in the graph."""
        return self._graph.number_of_edges()

    def add_entity(self, entity: Entity) -> None:
        """Add entity to graph with temporal metadata.

        Args:
            entity: Entity to add to the graph.
        """
        self._graph.add_node(entity.id, entity_type=entity.entity_type)
        self._entity_index[entity.id] = entity

        if entity.symbol:
            self._symbol_index[entity.symbol.upper()] = entity.id

        self._type_index[entity.entity_type].add(entity.id)
        logger.debug("Added entity: %s (%s)", entity.name, entity.entity_type.value)

    def add_relationship(self, relationship: Relationship) -> bool:
        """Add relationship between entities.

        Args:
            relationship: Relationship to add.

        Returns:
            True if added successfully, False if entities not found.
        """
        if relationship.source_id not in self._entity_index:
            logger.warning("Source entity %s not found", relationship.source_id)
            return False

        if relationship.target_id not in self._entity_index:
            logger.warning("Target entity %s not found", relationship.target_id)
            return False

        self._graph.add_edge(
            relationship.source_id,
            relationship.target_id,
            rel_type=relationship.relationship_type,
            strength=relationship.strength,
            temporal=relationship.temporal,
        )

        logger.debug(
            "Added relationship: %s -> %s (%s)",
            relationship.source_id,
            relationship.target_id,
            relationship.relationship_type.value,
        )
        return True

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID.

        Args:
            entity_id: Unique entity identifier.

        Returns:
            Entity if found, None otherwise.
        """
        return self._entity_index.get(entity_id)

    def get_entity_by_symbol(self, symbol: str) -> Optional[Entity]:
        """Get entity by ticker symbol.

        Args:
            symbol: Ticker symbol (case-insensitive).

        Returns:
            Entity if found, None otherwise.
        """
        entity_id = self._symbol_index.get(symbol.upper())
        if entity_id:
            return self._entity_index.get(entity_id)
        return None

    def get_entities_by_type(self, entity_type: EntityType) -> list[Entity]:
        """Get all entities of a specific type.

        Args:
            entity_type: Type of entities to retrieve.

        Returns:
            List of entities matching the type.
        """
        entity_ids = self._type_index.get(entity_type, set())
        return [
            self._entity_index[eid] for eid in entity_ids if eid in self._entity_index
        ]

    def get_related_entities(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        max_depth: int = 2,
        as_of: Optional[datetime] = None,
    ) -> list[tuple[Entity, Relationship]]:
        """Get related entities with optional filters.

        Args:
            entity_id: Starting entity ID.
            relationship_type: Filter by relationship type (None = all).
            max_depth: Maximum traversal depth.
            as_of: Temporal filter (None = current time).

        Returns:
            List of (entity, relationship) tuples.
        """
        if entity_id not in self._entity_index:
            return []

        as_of = as_of or datetime.now(timezone.utc)
        results: list[tuple[Entity, Relationship]] = []
        visited = {entity_id}
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            if depth >= max_depth:
                continue

            for neighbor_id in self._graph.neighbors(current_id):
                if neighbor_id in visited:
                    continue

                visited.add(neighbor_id)
                edge_data = self._graph[current_id][neighbor_id]
                temporal: TemporalMetadata = edge_data.get(
                    "temporal", TemporalMetadata()
                )
                if as_of and temporal.valid_until and as_of > temporal.valid_until:
                    continue

                rel_type: RelationshipType = edge_data.get("rel_type")
                if relationship_type and rel_type != relationship_type:
                    continue

                entity = self._entity_index.get(neighbor_id)
                if entity:
                    rel = Relationship(
                        id=f"{current_id}_{neighbor_id}_{rel_type.value}",
                        source_id=current_id,
                        target_id=neighbor_id,
                        relationship_type=rel_type,
                        strength=edge_data.get("strength", 1.0),
                        temporal=temporal,
                    )
                    results.append((entity, rel))
                    queue.append((neighbor_id, depth + 1))

        return results

    def get_incoming_relationships(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        as_of: Optional[datetime] = None,
    ) -> list[tuple[Entity, Relationship]]:
        """Get entities that have relationships pointing to this entity.

        Args:
            entity_id: Target entity ID.
            relationship_type: Filter by relationship type.
            as_of: Temporal filter.

        Returns:
            List of (source_entity, relationship) tuples.
        """
        if entity_id not in self._entity_index:
            return []

        as_of = as_of or datetime.now(timezone.utc)
        results = []

        for predecessor_id in self._graph.predecessors(entity_id):
            edge_data = self._graph[predecessor_id][entity_id]
            temporal: TemporalMetadata = edge_data.get("temporal", TemporalMetadata())

            if as_of and temporal.valid_until and as_of > temporal.valid_until:
                continue

            rel_type: RelationshipType = edge_data.get("rel_type")
            if relationship_type and rel_type != relationship_type:
                continue

            entity = self._entity_index.get(predecessor_id)
            if entity:
                rel = Relationship(
                    id=f"{predecessor_id}_{entity_id}_{rel_type.value}",
                    source_id=predecessor_id,
                    target_id=entity_id,
                    relationship_type=rel_type,
                    strength=edge_data.get("strength", 1.0),
                    temporal=temporal,
                )
                results.append((entity, rel))

        return results

    def remove_entity(self, entity_id: str) -> bool:
        """Remove entity and all its relationships.

        Args:
            entity_id: Entity ID to remove.

        Returns:
            True if removed, False if not found.
        """
        entity = self._entity_index.get(entity_id)
        if not entity:
            return False

        self._graph.remove_node(entity_id)
        del self._entity_index[entity_id]

        if entity.symbol:
            self._symbol_index.pop(entity.symbol.upper(), None)

        self._type_index.get(entity.entity_type, set()).discard(entity_id)
        return True

    def sweep_expired(self, as_of: Optional[datetime] = None) -> int:
        """Remove expired entities and their relationships.

        Args:
            as_of: Reference time (None = current time).

        Returns:
            Number of entities removed.
        """
        as_of = as_of or datetime.now(timezone.utc)
        expired_ids = []

        for entity_id, entity in self._entity_index.items():
            if entity.temporal.is_expired(as_of):
                expired_ids.append(entity_id)

        for entity_id in expired_ids:
            self.remove_entity(entity_id)

        if expired_ids:
            logger.info("Swept %d expired entities", len(expired_ids))

        return len(expired_ids)

    def get_stats(self) -> dict:
        """Get graph statistics.

        Returns:
            Dictionary with graph statistics.
        """
        degrees = dict(self._graph.degree()) if self._entity_index else {}
        avg_degree = sum(degrees.values()) / max(len(self._entity_index), 1)

        return {
            "total_entities": len(self._entity_index),
            "total_relationships": self._graph.number_of_edges(),
            "entities_by_type": {
                t.value: len(ids) for t, ids in self._type_index.items() if ids
            },
            "avg_degree": round(avg_degree, 2),
            "connected_components": nx.number_weakly_connected_components(self._graph)
            if self._entity_index
            else 0,
        }

    def clear(self) -> None:
        """Clear all entities and relationships."""
        self._graph.clear()
        self._entity_index.clear()
        self._symbol_index.clear()
        self._type_index = {t: set() for t in EntityType}
