# Specification: Intelligence (Vector Memory Loop) v2

## 1. Objective
Deeply integrate the `pgvector` memory system (via the canonical `JournalIndexer`) and a Temporal Knowledge Graph into the strategy scan cycles. This enables agents to "remember" market contexts, "recall" historical performance, and adapt behavior dynamically. This v2 spec incorporates audit-driven guardrails for LLM budgeting and structured logging.

## 2. Architecture & Design

### A. Persistence & Indexing (Postgres + JournalIndexer)
- **Unified Store:** Utilize the primary **PostgreSQL 16** instance for all memory and graph storage.
- **Vector Canonicalization:** All vector operations **MUST** use `JournalIndexer` (trading/journal/indexer.py). No parallel vector wrappers will be created.
- **KG Schema:** Implement the Temporal Knowledge Graph within a dedicated `kg` schema in Postgres, utilizing native concurrency controls and indexing.

### B. Temporal Knowledge Graph (Postgres Implementation)
- **Bi-Temporal Models:** Track `kg.entities` and `kg.triples` with `valid_from` and `valid_until` timestamps.
- **Graph Ingestion:** Async writers wired into `TaoshiBridge`, `Evaluator`, and `RegimeManager`.
- **Feature Flag:** Ingestion is controlled by the `STA_KNOWLEDGE_GRAPH_ENABLED` environment variable (default: `false`).
- **Maintenance:** Include a `sweep_expired()` background task to manage graph sprawl.

### C. Layered Agent Context (L0 + L1)
- **L0 (Identity):** Static agent metadata (~50-100 tokens).
- **L1 (Performance Story):** Dynamic summary of top wins/losses filtered by the current regime, retrieved via `JournalIndexer` (~200-500 tokens).
- **Context Injection:** Applied to the system prompt of the existing 13 agents.

### D. Guardrails & Instrumentation
- **LLM Budgeting:** Implement `max_calls_per_scan` and `monthly_token_quota` in `agents.yaml`.
- **Structured Logging:** Every memory write, KG update, and context generation **MUST** emit a structured event (e.g., `kg.triple_added`, `memory.deduplicated`) via `trading/utils/logging.py`.
- **Agent Identity:** Transition from a shared `X-API-Key` to per-agent identifiers for KG read/write auditing.

## 3. Tech Stack
- **Runtime:** Python 3.13 (FastAPI).
- **Models:** `claude-sonnet-4-6` (Default/L1 generation), `claude-opus-4-6` (ReACT/Deep Analysis).
- **Database:** PostgreSQL 16 + `pgvector`.

## 4. Risks & Mitigations
- **LLM Runaway Costs:** Mitigated by per-agent token quotas and the Phase 4 budget enforcement.
- **Loop Latency:** Mitigated by async "fire-and-forget" KG writes and the `STA_KNOWLEDGE_GRAPH_ENABLED` flag.
- **Parallel Stream Conflicts:** Mitigated by coordination with the `opencode` stream via shared task tracking in `plan.md`.