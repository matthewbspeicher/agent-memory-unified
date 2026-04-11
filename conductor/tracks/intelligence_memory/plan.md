# Implementation Plan: Intelligence (Vector Memory Loop) v2

## Phase 1: Foundation & Efficiency [x]
* land the "quick wins" from the audit and MemPalace roadmap.

- [x] **Task 1: Database Hardening (Postgres Migration Prep)** [x]
    - Ensure all SQLite connections in `trading/storage/memory.py` use `PRAGMA journal_mode=WAL` (immediate fix).
    - Design the `kg` schema migrations for PostgreSQL.
- [x] **Task 2: Pattern Pre-Filter & Event Logging** [x]
    - Implement the lightweight `has_knowledge_signal` filter in `.claude/knowledge/scripts/flush.py`.
    - Instrument the memory write path with structured events (`log_event("memory.write")`).
- [x] **Task 3: Content-Hash Deduplication** [x]
    - Implement MD5 hashing in `LocalMemoryStore` to prevent redundant vector storage.

## Phase 2: Temporal Knowledge Graph (Postgres) [x]
* Build the time-aware graph using the canonical database.

- [x] **Task 4: KG Schema Implementation** [x]
    - Apply Postgres migrations for `kg.entities` and `kg.triples`.
    - Implement `PostgresKnowledgeGraph` backend using the shared connection pool.
- [x] **Task 5: Pipeline Integration & Feature Flag** [x]
    - Add async KG writers to `TaoshiBridge` and `MinerEvaluator`.
    - Wrap all KG ingestion logic in `STA_KNOWLEDGE_GRAPH_ENABLED` guard.
- [x] **Task 6: Graph Maintenance** [x]
    - Implement the `sweep_expired()` routine to manage triple TTLs.

## Phase 3: Intelligent Agent Loop (L0 + L1) [x]
* Leverage JournalIndexer to feed performance context to agents.

- [x] **Task 7: Layered Context Generation** [x]
    - Implement L0/L1 generation in `SqlPromptStore` using `JournalIndexer` for win/loss retrieval.
    - Instrument generation with `log_event("agent.context_generated")`.
- [x] **Task 8: LLM Budget Enforcement** [x]
    - Add `max_calls_per_scan` schema to `agents.yaml` and enforce in `AgentRunner`.
- [x] **Task 9: ReACT Analyst Agent** [x]
    - Deploy `ReactAnalystAgent` using `claude-opus-4-6` for deep multi-hop reasoning.

## Phase 4: Structured Ingestion & Audit [x]
* Scaling and final security hardening.

- [x] **Task 10: Rule-Based Entity Extraction** [x]
    - Implement a narrow, rule-based `EntityExtractor` for news headlines (regex/keyword fallback).
- [x] **Task 11: Agent-Level Identity** [x]
    - Migrate KG endpoints to use per-agent identity tokens instead of a single shared API key.

---

## Quality Gates
- [ ] All KG roundtrip integration tests pass against Postgres.
- [ ] Manual verify: `log_event` output appears in structured logs for every memory write.
- [ ] Manual verify: Agent system prompts contain correctly formatted L0/L1 performance stories.
- [ ] LLM Budget: Verify agent execution halts if `max_calls_per_scan` is exceeded.
