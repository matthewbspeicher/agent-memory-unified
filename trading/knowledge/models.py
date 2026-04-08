"""Market knowledge graph data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class EntityType(Enum):
    COMPANY = "company"
    SECTOR = "sector"
    MACRO_INDICATOR = "macro_indicator"
    POLICY = "policy"
    EVENT = "event"
    EARNINGS = "earnings"
    COMMODITY = "commodity"
    CRYPTO = "crypto"


class RelationshipType(Enum):
    BELONGS_TO_SECTOR = "belongs_to_sector"
    AFFECTED_BY_POLICY = "affected_by_policy"
    CORRELATED_WITH = "correlated_with"
    COMPETES_WITH = "competes_with"
    SUPPLIES = "supplies"
    EARNINGS_DATE = "earnings_date"
    PART_OF_EVENT = "part_of_event"
    AFFECTS = "affects"


@dataclass
class TemporalMetadata:
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    confidence: float = 1.0

    def is_valid_at(self, timestamp: datetime) -> bool:
        if self.valid_from and timestamp < self.valid_from:
            return False
        if self.valid_until and timestamp > self.valid_until:
            return False
        return True

    def is_expired(self, as_of: Optional[datetime] = None) -> bool:
        as_of = as_of or datetime.now(timezone.utc)
        return self.valid_until is not None and as_of > self.valid_until


@dataclass
class Entity:
    id: str
    entity_type: EntityType
    name: str
    symbol: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    temporal: TemporalMetadata = field(default_factory=TemporalMetadata)


@dataclass
class Relationship:
    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    strength: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    temporal: TemporalMetadata = field(default_factory=TemporalMetadata)
