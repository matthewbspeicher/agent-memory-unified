# Research: MiroFish Swarm Intelligence Engine

## Executive Summary

**MiroFish** is a next-generation AI prediction engine powered by multi-agent technology (51.9k GitHub stars). It constructs high-fidelity parallel digital worlds where thousands of intelligent agents with independent personalities, long-term memory, and behavioral logic freely interact and undergo social evolution.

**Key Insight**: MiroFish's swarm intelligence approach offers valuable patterns for enhancing our agent-memory-unified project's multi-agent coordination, memory systems, and knowledge graph capabilities.

---

## MiroFish Architecture Overview

### Core Concept
```
Seed Materials (news, reports, stories)
    ↓
Graph Building (knowledge graph construction)
    ↓
Environment Setup (agent personas, simulation config)
    ↓
Simulation (multi-platform parallel execution)
    ↓
Report Generation (ReACT-based analysis)
    ↓
Deep Interaction (chat with simulated agents)
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python 3.11-3.12, Flask | API server, simulation engine |
| **Frontend** | Vue.js, Pinia | 5-step workflow UI |
| **Memory** | Zep Cloud | Knowledge graph, entity storage |
| **Simulation** | OASIS (CAMEL-AI) | Social media simulation framework |
| **LLM** | OpenAI-compatible API | Agent behavior, report generation |

---

## Key Architectural Patterns

### 1. Dual-Layer Memory Architecture

**Pattern**: Separate persistent and runtime memory for different access patterns.

```
┌─────────────────────────────────────────────────────────────┐
│                    MiroFish Memory System                   │
├─────────────────────────────────────────────────────────────┤
│  Long-Term Memory (Zep Graph)                              │
│  ├─ Entity nodes (UUID, labels, summaries)                 │
│  ├─ Relationship edges (facts, timestamps)                 │
│  ├─ Temporal tracking (created_at, valid_at, invalid_at)   │
│  └─ Persistent across sessions                             │
├─────────────────────────────────────────────────────────────┤
│  Short-Term Memory (Runtime)                               │
│  ├─ Recent 50 actions buffer (per agent)                   │
│  ├─ Platform-specific state tracking                       │
│  ├─ In-memory with fast access                             │
│  └─ Cleared after simulation                               │
└─────────────────────────────────────────────────────────────┘
```

**Key Files**:
- `/tmp/mirofish/backend/app/services/zep_graph_memory_updater.py` - Real-time sync to Zep
- `/tmp/mirofish/backend/app/services/simulation_runner.py` - Runtime buffer management

### 2. Knowledge Graph Construction Pipeline

**Pattern**: Structured extraction from unstructured text with ontology-driven entity/relationship discovery.

```
Text Documents
    ↓
Text Chunking (configurable size/overlap)
    ↓
Ontology Definition (entity types + relationships)
    ↓
Zep Processing (LLM-based entity extraction)
    ↓
Graph Storage (nodes + edges with temporal metadata)
```

**Key Files**:
- `/tmp/mirofish/backend/app/services/graph_builder.py` - Main graph construction
- `/tmp/mirofish/backend/app/services/ontology_generator.py` - LLM-based ontology definition
- `/tmp/mirofish/backend/app/services/text_processor.py` - Text chunking

### 3. Rich Agent Persona System

**Pattern**: LLM-enhanced agent profiles with multi-dimensional attributes.

```python
Agent Persona = {
    "name": "Zhang Wei",
    "bio": "32-year-old tech entrepreneur...",
    "age": 32,
    "gender": "male",
    "mbti": "ENTJ",
    "profession": "Software Engineer",
    "interests": ["AI", "startups", "crypto"],
    "personality_traits": ["ambitious", "analytical"],
    "social_network": {...}  # Connections to other agents
}
```

**Key Files**:
- `/tmp/mirofish/backend/app/services/oasis_profile_generator.py` - LLM-based persona generation
- `/tmp/mirofish/backend/app/services/simulation_config_generator.py` - Simulation parameter generation

### 4. Real-Time Memory Updates During Simulation

**Pattern**: Queue-based batch processing with retry logic for reliable memory synchronization.

```
Agent Action (create_post, like, comment)
    ↓
Action Logger (JSONL format)
    ↓
Memory Updater (queue-based)
    ↓
Natural Language Conversion
    ↓
Zep Graph Update (batch, retry with backoff)
```

**Key Files**:
- `/tmp/mirofish/backend/app/services/zep_graph_memory_updater.py` - Queue-based batch processor
- `/tmp/mirofish/backend/app/services/simulation_runner.py` - Action monitoring

### 5. ReACT-Based Report Generation

**Pattern**: Multi-round reasoning with tool calling for deep analysis.

```
User Query
    ↓
ReportAgent (ReACT loop)
    ├─ Reason: Analyze question
    ├─ Act: Call tools (search graph, query entities)
    ├─ Observe: Process results
    └─ Repeat until satisfied
    ↓
Final Report (with citations)
```

**Key Files**:
- `/tmp/mirofish/backend/app/services/report_agent.py` - ReACT implementation
- `/tmp/mirofish/backend/app/services/zep_tools.py` - Graph search tools

### 6. Multi-Platform Simulation Abstraction

**Pattern**: Platform-agnostic agent actions with platform-specific adapters.

```python
# Platform-agnostic actions
AgentAction = {
    "type": "CREATE_POST",
    "content": "...",
    "target": "timeline"
}

# Platform adapters
TwitterAdapter = {
    "CREATE_POST": twitter.create_tweet,
    "LIKE_POST": twitter.like_tweet,
    ...
}

RedditAdapter = {
    "CREATE_POST": reddit.submit_post,
    "CREATE_COMMENT": reddit.comment,
    ...
}
```

---

## Comparison with agent-memory-unified

### Current Architecture (agent-memory-unified)

```
┌─────────────────────────────────────────────────────────────┐
│              agent-memory-unified Memory System             │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Developer Knowledge Base (.claude/knowledge/)     │
│  ├─ daily/ (immutable conversation logs)                    │
│  ├─ knowledge/ (compiled articles: concepts, connections)   │
│  ├─ index.md (master catalog for retrieval)                 │
│  ├─ Hooks (SessionStart, SessionEnd, PreCompact)            │
│  └─ LLM compiler (compile.py)                               │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Trading Engine Memory (trading/)                  │
│  ├─ TradeReflector (trade memory + deep reflection)         │
│  ├─ MetaLearner (XGBoost signal combination)                │
│  ├─ JournalIndexer (HNSW vector search, 384-dim)            │
│  ├─ RegimeMemoryManager (HMM-based regime detection)        │
│  ├─ MemoryConsolidator (LLM-powered synthesis)              │
│  └─ SignalBus (agent-to-agent pub/sub)                      │
├─────────────────────────────────────────────────────────────┤
│  Agent System (trading/agents/)                             │
│  ├─ 13 configured agents (RSI, volume, Kalshi, etc.)        │
│  ├─ Base Agent with memory injection                        │
│  ├─ ManagerAgent for regime monitoring                      │
│  └─ YAML-based configuration                                │
└─────────────────────────────────────────────────────────────┘
```

### Gap Analysis

| Capability | MiroFish | agent-memory-unified | Gap |
|------------|----------|---------------------|-----|
| **Knowledge Graph** | ✅ Zep Cloud with temporal tracking | ❌ No graph structure | **HIGH** |
| **Rich Agent Personas** | ✅ LLM-generated multi-dimensional profiles | ❌ Basic YAML config only | **HIGH** |
| **Real-Time Memory Sync** | ✅ Queue-based batch processing | ⚠️ TradeReflector (simpler) | **MEDIUM** |
| **Multi-Platform Simulation** | ✅ Twitter, Reddit abstraction | ❌ Single platform (trading) | **LOW** (different domain) |
| **ReACT Report Generation** | ✅ Multi-round reasoning with tools | ⚠️ Basic report generation | **MEDIUM** |
| **Swarm Coordination** | ✅ Emergence from agent interactions | ⚠️ SignalBus (simpler) | **MEDIUM** |
| **Temporal Memory** | ✅ Valid/invalid timestamps on edges | ❌ No temporal tracking | **HIGH** |
| **Persona-Driven Behavior** | ✅ MBTI, interests, personality traits | ❌ Strategy-based only | **HIGH** |

---

## Key Learnings to Incorporate

### 1. Knowledge Graph Layer (HIGH PRIORITY)

**Current Gap**: We have flat knowledge articles (concepts, connections) but no graph structure with entities and relationships.

**MiroFish Pattern**: Zep Cloud graph with:
- Entity nodes (UUID, labels, summaries)
- Relationship edges (facts, timestamps)
- Temporal validity tracking

**Proposed Implementation**:
```python
# New module: .claude/knowledge/graph/
knowledge/
├── graph/
│   ├── entities/          # Entity nodes (YAML + markdown)
│   │   ├── person-zhang-wei.md
│   │   ├── concept-swarm-intelligence.md
│   │   └── project-mirofish.md
│   ├── relationships/     # Relationship edges
│   │   ├── zhang-wei-contributed-to-mirofish.md
│   │   └── mirofish-uses-oasis.md
│   └── graph.json         # Machine-readable graph structure
├── concepts/              # Keep existing
├── connections/           # Keep existing
└── index.md              # Enhanced with graph statistics
```

**Benefits**:
- Query: "Who contributed to projects that use swarm intelligence?"
- Temporal: "What concepts were valid during Q1 2026?"
- Inference: "If A relates to B and B relates to C, what's the A→C relationship?"

### 2. Rich Agent Personas for Trading Agents (HIGH PRIORITY)

**Current Gap**: Trading agents defined by strategy parameters only (RSI threshold, volume multiplier).

**MiroFish Pattern**: Multi-dimensional personas:
- Name, bio, age, profession
- MBTI personality type
- Interests, values, communication style
- Social network (connections to other agents)

**Proposed Enhancement**:
```yaml
# Enhanced agents.yaml
agents:
  - name: rsi_scanner
    strategy: rsi
    persona:
      name: "Technical Tina"
      bio: "Conservative technical analyst who trusts indicators over narratives"
      mbti: "ISTJ"
      risk_tolerance: "low"
      communication_style: "data-driven"
      trusted_sources: ["rsi", "macd", "bollinger"]
      distrusted_sources: ["twitter_sentiment", "news"]
    parameters:
      rsi_threshold: 30
```

**Benefits**:
- Agents can explain decisions in terms of their persona
- Meta-learner can weight signals based on agent personality traits
- Human-readable agent explanations: "Technical Tina avoided this trade because RSI wasn't oversold"

### 3. Real-Time Memory Updates with Queue Processing (MEDIUM PRIORITY)

**Current Gap**: TradeReflector writes memories synchronously, no batch processing or retry logic.

**MiroFish Pattern**: Queue-based batch processor:
- Actions queued in memory
- Batch processing (default 5 per batch)
- Exponential backoff retry
- Natural language conversion of structured actions

**Proposed Enhancement**:
```python
# Enhanced TradeReflector with queue
class QueuedTradeReflector:
    def __init__(self):
        self.memory_queue = asyncio.Queue()
        self.batch_size = 5
        self.retry_config = {"max_retries": 3, "backoff_factor": 2}
    
    async def reflect(self, trade: TradeMemory):
        # Queue the trade for async processing
        await self.memory_queue.put(trade)
        
    async def process_queue(self):
        batch = []
        while len(batch) < self.batch_size:
            batch.append(await self.memory_queue.get())
        await self._write_batch(batch)
```

**Benefits**:
- Non-blocking trade reflection (don't slow down trading loop)
- Reliable writes with retry logic
- Batch efficiency for vector index updates

### 4. Temporal Memory Tracking (HIGH PRIORITY)

**Current Gap**: No temporal metadata on memories. We don't know when concepts became valid/invalid.

**MiroFish Pattern**: Temporal validity on graph edges:
- `created_at`: When the relationship was discovered
- `valid_at`: When the relationship became true
- `invalid_at`: When the relationship stopped being true
- `expired_at`: When the relationship was marked stale

**Proposed Implementation**:
```yaml
# Enhanced article frontmatter
---
title: "RSI Oversold Pattern"
created: 2026-04-01
valid_from: 2026-04-01
valid_until: null  # null = still valid
sources:
  - "daily/2026-04-01.md"
  - "trades/2026-04-05.json"
confidence: 0.85
regime_applicability: ["quiet_range", "trending_bull"]
---
```

**Benefits**:
- Know which strategies worked in which market regimes
- Detect stale knowledge that needs refreshing
- Temporal queries: "What did we know about RSI patterns in March?"

### 5. ReACT-Based Deep Analysis (MEDIUM PRIORITY)

**Current Gap**: query.py loads entire KB into context. No multi-round reasoning with tool use.

**MiroFish Pattern**: ReportAgent with ReACT loop:
- Reason about the question
- Act: Call tools (search graph, query entities)
- Observe: Process results
- Repeat until satisfied

**Proposed Enhancement**:
```python
# Enhanced query.py with ReACT
class ReactQueryAgent:
    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.tools = {
            "search_graph": self.search_graph,
            "get_article": self.get_article,
            "list_concepts": self.list_concepts,
        }
    
    async def query(self, question: str) -> str:
        # ReACT loop
        while not self.satisfied:
            reasoning = await self.reason(question, context)
            action = await self.select_action(reasoning)
            observation = await self.execute_tool(action)
            context += observation
        return await self.synthesize(context)
```

**Benefits**:
- More efficient than loading entire KB
- Can handle complex multi-hop questions
- Provides reasoning trace for debugging

### 6. Swarm Coordination Enhancements (LOW PRIORITY)

**Current Gap**: SignalBus is simple pub/sub. No emergence patterns or collective intelligence.

**MiroFish Pattern**: Swarm emergence from individual interactions:
- Agents interact freely
- Collective patterns emerge
- Global behavior from local rules

**Proposed Enhancement**:
```python
# Enhanced SignalBus with emergence detection
class EmergentSignalBus(SignalBus):
    def __init__(self):
        super().__init__()
        self.interaction_history = []
        self.emergence_patterns = []
    
    async def detect_emergence(self):
        # Analyze interaction patterns for collective behavior
        patterns = await self.analyze_patterns(self.interaction_history)
        if patterns.significant:
            self.emergence_patterns.append(patterns)
            await self.notify_meta_agent(patterns)
```

**Benefits**:
- Detect when agents collectively converge on a signal
- Identify emergent market regimes
- Meta-agent can learn from collective intelligence

---

## Implementation Roadmap

### Phase 1: Foundation (2-3 weeks)
1. **Knowledge Graph Layer**
   - Design entity/relationship schema
   - Create graph/ directory structure
   - Implement graph.json generation
   - Add temporal metadata to articles

2. **Enhanced Agent Personas**
   - Extend agents.yaml with persona fields
   - Create persona generator utility
   - Update BaseAgent to use persona

### Phase 2: Memory Enhancement (2-3 weeks)
1. **Queue-Based Memory Updates**
   - Implement async memory queue
   - Add batch processing
   - Implement retry logic

2. **Temporal Tracking**
   - Add temporal fields to all memory models
   - Implement validity checking
   - Create temporal query interface

### Phase 3: Intelligence Layer (3-4 weeks)
1. **ReACT Query System**
   - Implement tool-calling query agent
   - Create graph search tools
   - Add reasoning trace logging

2. **Emergence Detection**
   - Extend SignalBus with pattern analysis
   - Implement emergence detection algorithms
   - Create meta-agent integration

---

## Technical Recommendations

### 1. Keep Zep Cloud Optional
MiroFish uses Zep Cloud for knowledge graph. We should:
- Support Zep Cloud as an option
- Also support local SQLite + USearch (like opencode-mem)
- Keep markdown files as source of truth

### 2. Gradual Persona Enhancement
Don't break existing agents:
- Add persona as optional field
- Default to strategy-based behavior if no persona
- Migrate agents incrementally

### 3. Backward Compatibility
All enhancements should be additive:
- Existing hooks continue to work
- Existing query.py continues to work
- New features are opt-in via configuration

### 4. Testing Strategy
- Unit tests for new memory queue
- Integration tests for graph construction
- Simulation tests for emergence detection

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Zep Cloud dependency** | Medium | Support local alternatives |
| **Persona complexity** | Low | Start simple, enhance gradually |
| **Queue reliability** | High | Implement proper retry + dead letter queue |
| **Graph performance** | Medium | Use efficient graph library (NetworkX) |
| **Emergence false positives** | Low | Require statistical significance |

---

## Conclusion

MiroFish offers valuable patterns for enhancing our multi-agent memory system:

1. **Knowledge Graph**: Add entity/relationship structure with temporal tracking
2. **Rich Personas**: Enhance agent configs with personality traits
3. **Queue-Based Memory**: Implement async, batched memory updates
4. **Temporal Tracking**: Add validity timestamps to all memories
5. **ReACT Queries**: Multi-round reasoning with tool use
6. **Swarm Coordination**: Detect emergent patterns from agent interactions

**Recommended Priority**:
1. Knowledge Graph Layer (enables powerful queries)
2. Rich Agent Personas (improves explainability)
3. Temporal Memory Tracking (critical for strategy evolution)
4. Queue-Based Memory Updates (reliability improvement)
5. ReACT Query System (efficiency improvement)
6. Swarm Coordination (nice-to-have)

---

*Research completed: 2026-04-08*
*Sources: GitHub repository analysis, architecture review, feature comparison*
*External repo: https://github.com/666ghj/MiroFish (51.9k stars)*