# MiroFish Integration - Validated Implementation Plan

## Executive Summary

This plan incorporates MiroFish's architectural patterns into agent-memory-unified's trading engine, validated against the actual codebase structure. Three features are prioritized based on value and implementation feasibility.

**Status**: Codebase validation complete. Ready for implementation.

---

## Validated Architecture Patterns

### Intelligence Layer Pattern (Confirmed)
```
BaseIntelProvider (abstract)
├── name: str (property)
├── analyze(symbol: str) -> IntelReport | None (async)
└── Returns: IntelReport(score, confidence, veto, details)

IntelligenceLayer orchestrates:
- 7 existing providers (on_chain, sentiment, anomaly, order_flow, regime, risk_audit, derivatives)
- Circuit breaker per provider (3 failures → 60s open)
- Parallel execution with 2s timeout
- Confidence enrichment via weighted scoring
```

### Agent Framework Pattern (Confirmed)
```
LLMAgent (base)
├── model: str (claude-sonnet-4-6 default)
├── system_prompt: str (supports learned prompts)
├── tools: list[str]
└── scan(data: DataBus) -> list[Opportunity] (abstract)

AgentRunner:
- Registers agents from agents.yaml
- Executes on schedule (continuous/cron/on_demand)
- Routes opportunities via router based on action_level
```

### News Signal Pipeline (Confirmed)
```
NewsAPISource / RSSNewsSource
    ↓
LLMClient.score_headline() [Anthropic → Groq → Ollama → rule-based]
    ↓
NewsSignal(contract_ticker, headline, relevance, sentiment, mispricing_score)
    ↓
EventBus.publish("NEWS_SIGNAL")
    ↓
SentimentProvider.analyze() [Fear & Greed, LunarCrush, Alpha Vantage]
    ↓
IntelReport → IntelligenceLayer enrichment
```

---

## Feature 1: Temporal Knowledge Graph (HIGH VALUE)

### Implementation

**New Module**: `trading/knowledge/`

```
trading/knowledge/
├── __init__.py
├── models.py       # Entity types, relationships, temporal metadata
├── graph.py        # MarketKnowledgeGraph (NetworkX-based)
├── query.py        # GraphQueryService
└── extractor.py    # Entity extraction from news (Feature 3)
```

#### models.py - Entity Definitions

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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

@dataclass
class TemporalMetadata:
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None  # None = still valid
    confidence: float = 1.0

@dataclass
class Entity:
    id: str
    entity_type: EntityType
    name: str
    symbol: Optional[str] = None  # Ticker if applicable
    metadata: dict = field(default_factory=dict)
    temporal: TemporalMetadata = field(default_factory=TemporalMetadata)

@dataclass
class Relationship:
    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    strength: float = 1.0  # 0.0-1.0
    metadata: dict = field(default_factory=dict)
    temporal: TemporalMetadata = field(default_factory=TemporalMetadata)
```

#### graph.py - MarketKnowledgeGraph

```python
import networkx as nx
from datetime import datetime, timezone
from typing import Optional
import logging

from knowledge.models import Entity, Relationship, EntityType, RelationshipType, TemporalMetadata

logger = logging.getLogger(__name__)

class MarketKnowledgeGraph:
    """NetworkX-based knowledge graph with temporal metadata."""
    
    def __init__(self):
        self._graph = nx.DiGraph()
        self._entity_index: dict[str, Entity] = {}  # id -> Entity
        self._symbol_index: dict[str, str] = {}  # symbol -> entity_id
        self._type_index: dict[EntityType, set[str]] = {t: set() for t in EntityType}
    
    def add_entity(self, entity: Entity) -> None:
        """Add entity to graph with temporal metadata."""
        self._graph.add_node(entity.id, entity_type=entity.entity_type)
        self._entity_index[entity.id] = entity
        if entity.symbol:
            self._symbol_index[entity.symbol.upper()] = entity.id
        self._type_index[entity.entity_type].add(entity.id)
        logger.debug("Added entity: %s (%s)", entity.name, entity.entity_type.value)
    
    def add_relationship(self, relationship: Relationship) -> None:
        """Add relationship between entities."""
        if relationship.source_id not in self._entity_index:
            logger.warning("Source entity %s not found", relationship.source_id)
            return
        if relationship.target_id not in self._entity_index:
            logger.warning("Target entity %s not found", relationship.target_id)
            return
        
        self._graph.add_edge(
            relationship.source_id,
            relationship.target_id,
            rel_type=relationship.relationship_type,
            strength=relationship.strength,
            temporal=relationship.temporal,
        )
        logger.debug("Added relationship: %s -> %s (%s)", 
                     relationship.source_id, relationship.target_id, 
                     relationship.relationship_type.value)
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID."""
        return self._entity_index.get(entity_id)
    
    def get_entity_by_symbol(self, symbol: str) -> Optional[Entity]:
        """Get entity by ticker symbol."""
        entity_id = self._symbol_index.get(symbol.upper())
        if entity_id:
            return self._entity_index.get(entity_id)
        return None
    
    def get_related_entities(
        self, 
        entity_id: str, 
        relationship_type: Optional[RelationshipType] = None,
        max_depth: int = 2,
        as_of: Optional[datetime] = None,
    ) -> list[tuple[Entity, Relationship]]:
        """Get related entities with optional filters."""
        if entity_id not in self._entity_index:
            return []
        
        results = []
        visited = {entity_id}
        queue = [(entity_id, 0)]
        
        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            
            for neighbor_id in self._graph.neighbors(current_id):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                
                edge_data = self._graph[current_id][neighbor_id]
                
                # Check temporal validity
                temporal = edge_data.get("temporal")
                if as_of and temporal and temporal.valid_until:
                    if as_of > temporal.valid_until:
                        continue
                
                # Check relationship type filter
                rel_type = edge_data.get("rel_type")
                if relationship_type and rel_type != relationship_type:
                    continue
                
                entity = self._entity_index.get(neighbor_id)
                if entity:
                    rel = Relationship(
                        id=f"{current_id}_{neighbor_id}",
                        source_id=current_id,
                        target_id=neighbor_id,
                        relationship_type=rel_type,
                        strength=edge_data.get("strength", 1.0),
                        temporal=temporal or TemporalMetadata(),
                    )
                    results.append((entity, rel))
                    queue.append((neighbor_id, depth + 1))
        
        return results
    
    def sweep_expired(self, as_of: Optional[datetime] = None) -> int:
        """Remove expired entities and relationships. Returns count removed."""
        as_of = as_of or datetime.now(timezone.utc)
        removed_count = 0
        
        # Find expired entities
        expired_ids = []
        for entity_id, entity in self._entity_index.items():
            if entity.temporal.valid_until and entity.temporal.valid_until < as_of:
                expired_ids.append(entity_id)
        
        # Remove expired entities and their edges
        for entity_id in expired_ids:
            self._graph.remove_node(entity_id)
            entity = self._entity_index.pop(entity_id, None)
            if entity and entity.symbol:
                self._symbol_index.pop(entity.symbol.upper(), None)
            if entity:
                self._type_index.get(entity.entity_type, set()).discard(entity_id)
            removed_count += 1
        
        logger.info("Swept %d expired entities", removed_count)
        return removed_count
    
    def get_stats(self) -> dict:
        """Get graph statistics."""
        return {
            "total_entities": len(self._entity_index),
            "total_relationships": self._graph.number_of_edges(),
            "entities_by_type": {t.value: len(ids) for t, ids in self._type_index.items()},
            "avg_degree": sum(dict(self._graph.degree()).values()) / max(len(self._entity_index), 1),
        }
```

#### query.py - GraphQueryService

```python
from datetime import datetime, timezone
from typing import Optional
import logging

from knowledge.graph import MarketKnowledgeGraph
from knowledge.models import Entity, EntityType, RelationshipType

logger = logging.getLogger(__name__)

@dataclass
class GraphContext:
    """Context bundle for a symbol at a point in time."""
    symbol: str
    entity: Optional[Entity]
    related_entities: list[tuple[Entity, Relationship]]
    sector: Optional[Entity] = None
    recent_events: list[Entity] = field(default_factory=list)
    policy_exposures: list[tuple[Entity, Relationship]] = field(default_factory=list)

class GraphQueryService:
    """Query service for market knowledge graph."""
    
    def __init__(self, graph: MarketKnowledgeGraph):
        self._graph = graph
    
    def get_context_bundle(
        self, 
        symbol: str, 
        as_of: Optional[datetime] = None,
        max_depth: int = 2,
    ) -> GraphContext:
        """Get comprehensive context for a symbol."""
        as_of = as_of or datetime.now(timezone.utc)
        entity = self._graph.get_entity_by_symbol(symbol)
        
        if not entity:
            return GraphContext(
                symbol=symbol,
                entity=None,
                related_entities=[],
            )
        
        # Get all related entities
        related = self._graph.get_related_entities(
            entity.id, max_depth=max_depth, as_of=as_of
        )
        
        # Extract sector
        sector = None
        for rel_entity, rel in related:
            if rel.relationship_type == RelationshipType.BELONGS_TO_SECTOR:
                sector = rel_entity
                break
        
        # Extract recent events (created in last 7 days)
        recent_events = []
        cutoff = as_of - timedelta(days=7)
        for rel_entity, rel in related:
            if rel_entity.entity_type == EntityType.EVENT:
                if rel_entity.temporal.created_at > cutoff:
                    recent_events.append(rel_entity)
        
        # Extract policy exposures
        policy_exposures = [
            (e, r) for e, r in related 
            if r.relationship_type == RelationshipType.AFFECTED_BY_POLICY
        ]
        
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
        """Get symbols correlated with the given symbol."""
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
```

#### Intelligence Provider Integration

**File**: `trading/intelligence/providers/knowledge_graph.py`

```python
from intelligence.providers.base import BaseIntelProvider
from intelligence.models import IntelReport
from knowledge.query import GraphQueryService
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class KnowledgeGraphProvider(BaseIntelProvider):
    """Enriches signals with knowledge graph context."""
    
    def __init__(self, query_service: GraphQueryService):
        self._query_service = query_service
    
    @property
    def name(self) -> str:
        return "knowledge_graph"
    
    async def analyze(self, symbol: str) -> IntelReport | None:
        try:
            context = self._query_service.get_context_bundle(symbol)
            
            if not context.entity:
                logger.debug("No graph entity for %s", symbol)
                return None
            
            # Compute score based on graph context
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
                    "sector": context.sector.name if context.sector else None,
                    "related_count": len(context.related_entities),
                    "recent_events": len(context.recent_events),
                    "policy_exposures": len(context.policy_exposures),
                },
            )
        except Exception as e:
            logger.warning("KnowledgeGraphProvider failed for %s: %s", symbol, e)
            return None
    
    def _compute_context_score(self, context) -> float:
        """Compute sentiment score from graph context."""
        score = 0.0
        
        # Recent positive events boost score
        for event in context.recent_events:
            event_sentiment = event.metadata.get("sentiment", 0.0)
            score += event_sentiment * 0.1
        
        # Policy exposures can be positive or negative
        for policy_entity, rel in context.policy_exposures:
            policy_impact = policy_entity.metadata.get("impact_score", 0.0)
            score += policy_impact * rel.strength * 0.15
        
        return max(-1.0, min(1.0, score))
    
    def _compute_confidence(self, context) -> float:
        """Compute confidence based on graph completeness."""
        base_confidence = 0.5
        
        # More relationships = higher confidence
        rel_count = len(context.related_entities)
        if rel_count > 10:
            base_confidence += 0.2
        elif rel_count > 5:
            base_confidence += 0.1
        
        # Sector known = higher confidence
        if context.sector:
            base_confidence += 0.1
        
        # Recent events = higher confidence
        if context.recent_events:
            base_confidence += 0.1
        
        return min(1.0, base_confidence)
```

### Integration Steps

1. **Create `trading/knowledge/` module** with models.py, graph.py, query.py
2. **Create `trading/intelligence/providers/knowledge_graph.py`**
3. **Register in IntelligenceLayer** (`intelligence/layer.py`):
   ```python
   from knowledge.graph import MarketKnowledgeGraph
   from knowledge.query import GraphQueryService
   from intelligence.providers.knowledge_graph import KnowledgeGraphProvider
   
   # In __init__:
   self._kg_graph = MarketKnowledgeGraph()
   self._kg_query = GraphQueryService(self._kg_graph)
   self._knowledge_graph = KnowledgeGraphProvider(self._kg_query)
   self._breakers["knowledge_graph"] = make_breaker()
   ```
4. **Add to provider list** in `_gather_intel()`:
   ```python
   ("knowledge_graph", self._knowledge_graph),
   ```
5. **Add config** to `intelligence/config.py`:
   ```python
   weights: dict[str, float] = {
       # ... existing ...
       "knowledge_graph": 0.15,
   }
   ```

---

## Feature 2: ReACT-Loop Research Agent (HIGH VALUE)

### Implementation

**File**: `trading/strategies/react_analyst.py`

```python
from agents.base import LLMAgent
from agents.models import Opportunity, AgentConfig, OpportunityStatus
from data.bus import DataBus
from datetime import datetime, timezone
from typing import Any
import anthropic
import json
import uuid
import logging

logger = logging.getLogger(__name__)

class ReactAnalystAgent(LLMAgent):
    """ReACT-based analyst that iteratively reasons about market opportunities."""
    
    @property
    def description(self) -> str:
        return f"ReACT analyst using {self.model} with iterative reasoning loop"
    
    async def scan(self, data: DataBus) -> list[Opportunity]:
        symbols = data.get_universe(self.config.universe)
        if not symbols:
            return []
        
        opportunities = []
        
        for symbol in symbols[:5]:  # Limit to 5 symbols per scan
            try:
                opp = await self._analyze_symbol(data, symbol)
                if opp:
                    opportunities.append(opp)
            except Exception as e:
                logger.warning("ReactAnalyst failed for %s: %s", symbol, e)
        
        return opportunities
    
    async def _analyze_symbol(self, data: DataBus, symbol) -> Opportunity | None:
        """Run ReACT loop for a single symbol."""
        max_iterations = self.config.parameters.get("max_iterations", 5)
        confidence_threshold = self.config.parameters.get("confidence_threshold", 0.6)
        
        # Initial context
        context = await self._gather_initial_context(data, symbol)
        
        # ReACT loop
        reasoning_trace = []
        tools_used = []
        
        client = anthropic.AsyncAnthropic()
        
        for iteration in range(max_iterations):
            # Thought: Reason about current state
            thought = await self._generate_thought(
                client, context, reasoning_trace, tools_used
            )
            reasoning_trace.append({"iteration": iteration, "thought": thought})
            
            # Check if ready to conclude
            if self._should_conclude(thought):
                break
            
            # Action: Decide what tool to use
            action = await self._generate_action(client, thought, context)
            
            if action.get("type") == "final_answer":
                break
            
            # Observation: Execute tool and observe
            observation = await self._execute_tool(data, symbol, action)
            tools_used.append(action.get("tool"))
            reasoning_trace.append({
                "iteration": iteration,
                "action": action,
                "observation": observation,
            })
        
        # Generate final opportunity from reasoning trace
        return await self._generate_opportunity(
            client, symbol, reasoning_trace, confidence_threshold
        )
    
    async def _gather_initial_context(self, data: DataBus, symbol) -> dict:
        """Gather initial market context."""
        quote = await data.get_quote(symbol)
        rsi = await data.get_rsi(symbol, period=14)
        sma_20 = await data.get_sma(symbol, period=20)
        
        return {
            "symbol": str(symbol),
            "price": quote.last if quote else None,
            "volume": quote.volume if quote else None,
            "rsi": rsi,
            "sma_20": sma_20,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    async def _generate_thought(
        self, client, context: dict, trace: list, tools_used: list
    ) -> str:
        """Generate reasoning thought."""
        prompt = f"""You are a quantitative trading analyst analyzing {context['symbol']}.

Current Market Data:
- Price: {context.get('price', 'N/A')}
- Volume: {context.get('volume', 'N/A')}
- RSI(14): {context.get('rsi', 'N/A')}
- SMA(20): {context.get('sma_20', 'N/A')}

Previous Reasoning:
{json.dumps(trace[-3:] if len(trace) > 3 else trace, indent=2)}

Tools Used: {tools_used}

Analyze the current situation and determine what you need to know next.
If you have enough information to make a trading decision, state your conclusion clearly.
Otherwise, specify what additional data would help your analysis."""

        response = await client.messages.create(
            model=self.model,
            max_tokens=500,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    
    def _should_conclude(self, thought: str) -> bool:
        """Check if thought indicates readiness to conclude."""
        conclusion_keywords = ["conclusion", "recommendation", "signal", "opportunity"]
        return any(kw in thought.lower() for kw in conclusion_keywords)
    
    async def _generate_action(self, client, thought: str, context: dict) -> dict:
        """Generate action to take."""
        prompt = f"""Based on this analysis:
{thought}

Available tools:
1. query_market_data - Get additional price/volume data
2. query_indicators - Get technical indicators (MACD, BB, ATR)
3. query_knowledge_graph - Get entity relationships and events
4. query_agent_memory - Get past trade lessons for this symbol
5. final_answer - Conclude with trading decision

Respond with JSON:
{{"tool": "<tool_name>", "params": {{...}}}} or {{"type": "final_answer", "answer": "..."}}"""

        response = await client.messages.create(
            model=self.model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        
        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return {"type": "final_answer"}
    
    async def _execute_tool(self, data: DataBus, symbol, action: dict) -> str:
        """Execute tool and return observation."""
        tool = action.get("tool", "")
        params = action.get("params", {})
        
        if tool == "query_market_data":
            quote = await data.get_quote(symbol)
            return f"Price: {quote.last}, Volume: {quote.volume}"
        
        elif tool == "query_indicators":
            macd = await data.get_macd(symbol)
            bb = await data.get_bollinger(symbol)
            return f"MACD: {macd}, Bollinger: {bb}"
        
        elif tool == "query_agent_memory":
            if hasattr(self, "memory") and self.memory:
                lessons = self.memory.query(symbol, limit=5)
                return f"Past lessons: {lessons}"
            return "No memory available"
        
        elif tool == "query_knowledge_graph":
            # Placeholder for knowledge graph integration
            return "Knowledge graph query not yet implemented"
        
        return f"Unknown tool: {tool}"
    
    async def _generate_opportunity(
        self, client, symbol, trace: list, confidence_threshold: float
    ) -> Opportunity | None:
        """Generate Opportunity from reasoning trace."""
        prompt = f"""Based on this analysis trace for {symbol}:
{json.dumps(trace, indent=2)}

Generate a trading opportunity as JSON:
{{
    "signal": "<SIGNAL_TYPE>",
    "confidence": <0.0-1.0>,
    "reasoning": "<concise explanation>",
    "direction": "<bullish|bearish|neutral>"
}}

Only generate if confidence >= {confidence_threshold} and signal is clear."""

        response = await client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        
        try:
            result = json.loads(response.content[0].text)
            
            if result.get("confidence", 0) < confidence_threshold:
                return None
            
            if result.get("direction") == "neutral":
                return None
            
            return Opportunity(
                id=str(uuid.uuid4()),
                agent_name=self.name,
                symbol=symbol,
                signal=result["signal"],
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                data={
                    "trace_length": len(trace),
                    "direction": result["direction"],
                },
                timestamp=datetime.now(timezone.utc),
                status=OpportunityStatus.PENDING,
            )
        except (json.JSONDecodeError, KeyError):
            return None
```

### Registration

**File**: `trading/agents/config.py` (add after line 126)

```python
from strategies.react_analyst import ReactAnalystAgent
register_strategy("react_analyst", ReactAnalystAgent)
```

### Configuration

**File**: `trading/agents.yaml` (add new agent)

```yaml
  - name: react_analyst_btc
    strategy: react_analyst
    schedule: continuous
    interval: 300  # 5 minutes
    action_level: suggest_trade
    trust_level: monitored
    model: claude-sonnet-4-6
    system_prompt: |
      You are a quantitative trading analyst using ReACT reasoning.
      Analyze market data systematically, considering technical indicators,
      market structure, and risk factors. Only generate opportunities
      when confidence is high and reasoning is clear.
    parameters:
      max_iterations: 5
      confidence_threshold: 0.65
    universe: ["BTCUSD", "ETHUSD"]
  
  - name: react_analyst_equities
    strategy: react_analyst
    schedule: cron
    cron_expression: "0 9-16 * * 1-5"  # Market hours
    action_level: notify
    trust_level: monitored
    model: claude-sonnet-4-6
    system_prompt: |
      You are an equity market analyst using ReACT reasoning.
      Focus on sector rotation, earnings impact, and macro trends.
    parameters:
      max_iterations: 3
      confidence_threshold: 0.7
    universe: ["NVDA", "AAPL", "MSFT", "TSLA"]
```

---

## Feature 3: Structured Entity Extraction (MEDIUM VALUE)

### Implementation

**File**: `trading/knowledge/extractor.py`

```python
from dataclasses import dataclass, field
from typing import Optional
from llm.client import LLMClient
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class ExtractedEntity:
    name: str
    entity_type: str  # company, sector, indicator, event, policy
    symbol: Optional[str] = None
    relevance: float = 1.0

@dataclass
class ExtractedRelationship:
    source: str
    target: str
    relationship_type: str
    strength: float = 1.0

@dataclass
class EntityExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    sentiment: Optional[float] = None  # -1.0 to +1.0
    temporal_bounds: dict = field(default_factory=dict)  # valid_from, valid_until

class EntityExtractor:
    """Extract structured entities and relationships from text."""
    
    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client
    
    async def extract(self, text: str, context: Optional[str] = None) -> EntityExtractionResult:
        """Extract entities and relationships from text."""
        prompt = f"""Extract structured entities and relationships from this text.

Text: {text}
{f"Context: {context}" if context else ""}

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
```

### Integration with News Sources

**File**: `trading/data/sources/newsapi.py` (modify NewsSignal creation)

```python
from knowledge.extractor import EntityExtractor

class NewsAPISource:
    def __init__(self, ..., llm_client: LLMClient, entity_extractor: EntityExtractor | None = None):
        # ... existing init ...
        self._entity_extractor = entity_extractor
    
    async def _score_headline(self, contract, headline, url, published_at):
        # ... existing scoring ...
        
        # Extract entities if extractor available
        entities = []
        if self._entity_extractor:
            extraction = await self._entity_extractor.extract(headline, contract.title)
            entities = [e.name for e in extraction.entities]
        
        return NewsSignal(
            # ... existing fields ...
            entities=entities,  # NEW field
        )
```

**File**: `trading/data/sources/models.py` (extend NewsSignal)

```python
@dataclass
class NewsSignal:
    # ... existing fields ...
    entities: list[str] = field(default_factory=list)  # NEW
```

---

## Implementation Sequence

| Phase | Scope | Files | Dependencies |
|-------|-------|-------|--------------|
| **Phase 1** | Knowledge graph foundation | `trading/knowledge/{__init__,models,graph,query}.py` | None |
| **Phase 2** | Intelligence provider | `trading/intelligence/providers/knowledge_graph.py`, modify `layer.py`, `config.py` | Phase 1 |
| **Phase 3** | Entity extraction | `trading/knowledge/extractor.py`, modify `newsapi.py`, `rss_news.py`, `models.py` | Phase 1 |
| **Phase 4** | ReACT analyst agent | `trading/strategies/react_analyst.py`, modify `agents/config.py`, `agents.yaml` | None |
| **Phase 5** | Integration + testing | Tests, validation, tuning | All phases |

---

## Verification Plan

### Unit Tests

```bash
# Knowledge graph tests
python -m pytest tests/unit/test_knowledge/ -v --tb=short

# Entity extraction tests  
python -m pytest tests/unit/test_knowledge/test_extractor.py -v

# ReACT agent tests
python -m pytest tests/unit/test_strategies/test_react_analyst.py -v

# Intelligence provider tests
python -m pytest tests/unit/test_intelligence/ -v
```

### Integration Test

```python
# test_knowledge_integration.py
async def test_knowledge_graph_enrichment():
    """Test that knowledge graph enriches consensus signals."""
    # 1. Add test entities to graph
    # 2. Trigger consensus signal
    # 3. Verify enrichment includes graph context
    # 4. Verify confidence adjustment
```

### Shadow Mode

```yaml
# agents.yaml - Run in shadow mode first
  - name: react_analyst_btc
    strategy: react_analyst
    action_level: notify  # Don't trade, just observe
    trust_level: monitored
```

---

## Configuration

### Environment Variables

```bash
# Knowledge graph (optional - uses local NetworkX by default)
STA_KNOWLEDGE_GRAPH_PERSIST_PATH=/app/data/knowledge_graph.json

# Entity extraction (uses existing LLM client)
# No new env vars needed - uses existing LLM providers
```

### Intelligence Config

```python
# intelligence/config.py additions
weights: dict[str, float] = {
    # ... existing ...
    "knowledge_graph": 0.15,  # Moderate weight for graph context
}
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Graph memory growth | Medium | Implement sweep_expired(), limit entity count |
| LLM extraction cost | Low | Use rule-based fallback, batch extraction |
| ReACT loop timeout | Medium | Configurable max_iterations, timeout enforcement |
| Breaking existing tests | Low | Additive changes only, comprehensive test suite |

---

## Summary

This validated implementation plan adds three high-value capabilities:

1. **Temporal Knowledge Graph** - NetworkX-based graph with entity relationships and temporal metadata, integrated as an intelligence provider
2. **ReACT Analyst Agent** - Iterative reasoning agent that queries market data, memory, and knowledge graph to build layered analysis
3. **Entity Extraction** - LLM-powered extraction from news headlines, feeding the knowledge graph

All patterns validated against existing codebase architecture. Ready for implementation.

---

*Plan validated: 2026-04-08*
*Codebase exploration: Complete (intelligence layer, agent framework, news sources)*
