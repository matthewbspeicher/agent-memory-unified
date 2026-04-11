"""Rule-based entity and relationship extraction for trading news.

Provides deterministic extraction of market entities (tickers, sectors, orgs)
and triples from text headlines without requiring LLM calls.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


class EntityExtractor:
    """Extracts trading entities and triples using regex and keyword rules."""

    # Ticker pattern: 2-5 uppercase letters, optionally prefixed with $
    TICKER_PATTERN = re.compile(r"\$?([A-Z]{2,5})\b")
    
    # Relationship keywords
    RELATIONSHIPS = {
        "partnership": ["partner", "collaborate", "joint venture", "integration"],
        "acquisition": ["acquire", "buyout", "merger", "purchase"],
        "sentiment_positive": ["bullish", "surge", "rally", "breakout", "upgrade"],
        "sentiment_negative": ["bearish", "crash", "plummet", "dump", "downgrade"],
        "listing": ["list", "listing", "exchange", "available on"],
    }

    def __init__(self):
        self.common_words = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "ANY"}

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        """Extract potential entities from text."""
        entities = []
        
        # 1. Extract Tickers
        tickers = self.TICKER_PATTERN.findall(text)
        for ticker in tickers:
            if ticker.upper() not in self.common_words:
                entities.append({
                    "id": ticker.upper(),
                    "name": ticker.upper(),
                    "type": "asset"
                })
        
        # 2. Extract specific orgs (heuristic: Title Case words > 3 chars)
        # Narrowed to avoid noise
        org_matches = re.findall(r"\b([A-Z][a-z]{3,})\b", text)
        for org in org_matches:
            if org.upper() not in self.common_words:
                entities.append({
                    "id": org.lower(),
                    "name": org,
                    "type": "organization"
                })
                
        return entities

    def extract_triples(self, text: str, source: str = "extractor") -> list[dict[str, Any]]:
        """Extract triples (subject-predicate-object) based on proximity and keywords."""
        triples = []
        entities = self.extract_entities(text)
        
        if not entities:
            return []

        text_lower = text.lower()
        now = datetime.now(timezone.utc).isoformat()

        # Rule 1: Relationship between two entities
        if len(entities) >= 2:
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    subj = entities[i]
                    obj = entities[j]
                    
                    for pred, keywords in self.RELATIONSHIPS.items():
                        if any(kw in text_lower for kw in keywords):
                            triples.append({
                                "subject": subj["id"],
                                "predicate": pred,
                                "object": obj["id"],
                                "confidence": 0.7,
                                "source": source,
                                "valid_from": now
                            })

        # Rule 2: Asset sentiment (if only one ticker found)
        if len(entities) == 1 and entities[0]["type"] == "asset":
            asset = entities[0]["id"]
            if any(kw in text_lower for kw in self.RELATIONSHIPS["sentiment_positive"]):
                triples.append({
                    "subject": asset,
                    "predicate": "has_sentiment",
                    "object": "bullish",
                    "confidence": 0.6,
                    "source": source,
                    "valid_from": now
                })
            elif any(kw in text_lower for kw in self.RELATIONSHIPS["sentiment_negative"]):
                triples.append({
                    "subject": asset,
                    "predicate": "has_sentiment",
                    "object": "bearish",
                    "confidence": 0.6,
                    "source": source,
                    "valid_from": now
                })

        return triples
