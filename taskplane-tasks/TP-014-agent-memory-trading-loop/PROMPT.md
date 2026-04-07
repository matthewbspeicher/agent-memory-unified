# Task: TP-014 - Agent Memory → Trading Loop Integration

**Created:** 2026-04-07
**Size:** L

## Review Level: 2 (Plan and Code)

**Assessment:** New integration between memory system and trading decisions. Novel pattern, multiple services.
**Score:** 5/8 — Blast radius: 2, Pattern novelty: 2, Security: 0, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-014-agent-memory-trading-loop/
```

## Mission

Wire the vector memory system into the trading strategy loop so agents can store and recall market patterns, previous trade outcomes, and market regime context. This is the core product vision — agents that learn from experience. Implement a `MemoryStore` that strategies can use to persist observations and query relevant historical context when making decisions.

## Dependencies

- **None**
- **None**
- **None**
- **External:** PostgreSQL with pgvector extension

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `CLAUDE.md` — architecture, pgvector setup
- `conductor/product.md` — memory system vision
- Decision from TP-013

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading, postgres with pgvector)

## File Scope

- `trading/memory/` (new directory)
- `trading/memory/store.py` (new — vector memory store)
- `trading/memory/embeddings.py` (new — text embedding for market observations)
- `trading/memory/models.py` (new — memory data models)
- `trading/agents/base.py` (add memory access to agent base class)
- `trading/strategies/bittensor_consensus.py` (use memory for context)
- `scripts/init-trading-tables.sql` (add memory tables with pgvector)
- `trading/tests/unit/test_memory/` (new)

## Steps

### Step 0: Preflight
- [ ] Read TP-013 decision on memory API location
- [ ] Read pgvector setup in PostgreSQL
- [ ] Read existing agent base class for extension points
- [ ] Check if any memory/embedding code already exists in the codebase

### Step 1: Create Memory Infrastructure
- [ ] Design memory schema: `agent_memories` table with pgvector embedding column
- [ ] Create `trading/memory/models.py` — Memory dataclass (content, embedding, metadata, timestamp, agent_name)
- [ ] Create `trading/memory/store.py` — MemoryStore with save/search/delete operations
- [ ] Create `trading/memory/embeddings.py` — simple embedding generation (sentence-transformers or OpenAI)
- [ ] Add tables to `scripts/init-trading-tables.sql`

### Step 2: Integrate with Agent Framework
- [ ] Add optional `memory_store` to agent base class
- [ ] Implement `remember(observation: str, metadata: dict)` and `recall(query: str, k: int) -> list[Memory]` convenience methods
- [ ] Wire MemoryStore into agent runner initialization

### Step 3: Add Trading Context Memories
- [ ] After each trade decision, store: market conditions, signal state, decision rationale, outcome
- [ ] Before each scan, recall relevant memories for current market conditions
- [ ] Store market regime observations (trending/ranging/volatile)

### Step 4: Write Tests
- [ ] Test memory store CRUD with pgvector
- [ ] Test similarity search returns relevant memories
- [ ] Test agent memory integration
- [ ] Test memory doesn't slow down scan cycle (<100ms overhead)

### Step 5: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 6: Documentation & Delivery
- [ ] Document memory system architecture
- [ ] Document how strategies use memory
- [ ] Discoveries logged

## Completion Criteria
- [ ] Agents can store and recall memories via pgvector
- [ ] Trading strategies use memory for context in decisions
- [ ] Memory search is fast (<100ms per query)
- [ ] Memory persists across restarts

## Git Commit Convention
- `feat(TP-014): complete Step N — description`

## Do NOT
- Add expensive LLM calls in the hot trading loop (embeddings only)
- Store raw market data in memory (summaries/observations only)
- Require the Laravel API to be running
- Add >50MB embedding models

---

## Amendments (Added During Execution)
