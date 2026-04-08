"""Entity extraction from text for knowledge graph population.

Uses LLM to extract structured entities and relationships from
unstructured text such as news headlines and articles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from llm.client import LLMClient

import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """Entity extracted from text."""

    name: str
    entity_type: str
    symbol: Optional[str] = None
    relevance: float = 1.0


@dataclass
class ExtractedRelationship:
    """Relationship extracted between entities."""

    source: str
    target: str
    relationship_type: str
    strength: float = 1.0


@dataclass
class EntityExtractionResult:
    """Result of entity extraction from text."""

    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    sentiment: Optional[float] = None
    temporal_bounds: dict = field(default_factory=dict)


EXTRACTION_PROMPT = """Extract structured entities and relationships from this text.

Text: {text}
{context_line}

Return ONLY valid JSON:
{{
    "entities": [
        {{"name": "NVDA", "type": "company", "symbol": "NVDA", "relevance": 0.95}}
    ],
    "relationships": [
        {{"source": "semiconductor tariffs", "target": "NVDA", "type": "affects", "strength": 0.8}}
    ],
    "sentiment": 0.3,
    "temporal_bounds": {{
        "valid_until": "2025-06-30"
    }}
}}

Entity types: company, sector, indicator, event, policy, commodity, crypto
Relationship types: affects, belongs_to, competes_with, correlated_with, part_of, caused_by"""


class EntityExtractor:
    """Extract structured entities and relationships from text.

    Uses LLM to identify market-relevant entities and their
    relationships from unstructured text.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def extract(
        self, text: str, context: Optional[str] = None
    ) -> EntityExtractionResult:
        """Extract entities and relationships from text.

        Args:
            text: Text to extract from (headline, article, etc.)
            context: Optional context (contract title, topic, etc.)

        Returns:
            EntityExtractionResult with extracted entities and relationships.
        """
        context_line = f"Context: {context}" if context else ""
        prompt = EXTRACTION_PROMPT.format(text=text, context_line=context_line)

        try:
            response = await self._llm.complete(
                prompt=prompt,
                max_tokens=500,
                temperature=0.1,
            )

            data = json.loads(response)

            entities = [
                ExtractedEntity(
                    name=e["name"],
                    entity_type=e["type"],
                    symbol=e.get("symbol"),
                    relevance=e.get("relevance", 1.0),
                )
                for e in data.get("entities", [])
            ]

            relationships = [
                ExtractedRelationship(
                    source=r["source"],
                    target=r["target"],
                    relationship_type=r["type"],
                    strength=r.get("strength", 1.0),
                )
                for r in data.get("relationships", [])
            ]

            return EntityExtractionResult(
                entities=entities,
                relationships=relationships,
                sentiment=data.get("sentiment"),
                temporal_bounds=data.get("temporal_bounds", {}),
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Entity extraction failed: %s", e)
            return EntityExtractionResult()
