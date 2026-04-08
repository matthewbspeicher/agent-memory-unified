# Compiled Knowledge Layer Implementation Plan

> **Author:** Codex
> **Date:** 2026-04-08
> **Status:** PROPOSED

---

## Goal
Add a compiled-knowledge layer to the live `trading/` system so agents can consume stable, revisioned Markdown pages plus fresh evidence instead of reconstructing context from raw fragments on every query.

This plan intentionally targets the active FastAPI trading stack, not the deprecated Laravel API.

---

## Why This Plan Exists

The repo already has three relevant systems:

1. Raw memory and shared observations via Remembr and the hybrid memory client.
2. Reflection and autopsy generation for closed trades.
3. Journal indexing for semantic recall.

What is missing is a durable synthesis layer that:

- preserves provenance,
- compiles repeated observations into stable pages,
- is inspectable by humans,
- and can be consumed by agents without forcing them to re-summarize the same facts.

This plan adds that layer without replacing the existing memory and journal systems.

---

## Non-Goals

- Do not revive or extend the deprecated Laravel `api/` service.
- Do not replace raw retrieval with compiled pages in phase 1.
- Do not trigger expensive LLM compilation on every Redis event.
- Do not allow direct UI edits to silently mutate machine-generated runtime knowledge.

---

## Existing Integration Points

These are the live seams this plan builds on:

- `trading/learning/trade_reflector.py`
- `trading/journal/autopsy.py`
- `trading/journal/manager.py`
- `trading/events/consumer_streams.py`
- `trading/api/routes/memory.py`
- `trading/learning/memory_client.py`
- `trading/api/app.py`
- `scripts/init-trading-tables.sql`
- `trading/storage/db.py`
- `frontend/src/pages/KnowledgeGraph.tsx`

---

## Target Architecture

The compiled-knowledge layer has four layers:

1. `knowledge_events`
- Append-only source of truth.
- Trade reflections, autopsies, market observations, regime changes, operator notes.

2. `atomic memories`
- Existing private/shared memory records from Remembr or local fallback.
- Retained for backward compatibility and fresh evidence retrieval.

3. `compiled pages`
- Markdown pages synthesized from `knowledge_events`.
- Revisioned, embedded, scoped, and auditable.

4. `annotations and overrides`
- Human-added notes and approved edits.
- Stored separately from machine-compiled revisions.

---

## Data Model

### Table 1: `knowledge_events`

Purpose: append-only event log for knowledge compilation.

Columns:

- `id UUID PRIMARY KEY`
- `namespace VARCHAR(255) NOT NULL`
- `scope_type VARCHAR(64) NOT NULL`
- `scope_key VARCHAR(255) NOT NULL`
- `event_type VARCHAR(128) NOT NULL`
- `slug_hint VARCHAR(255) NULL`
- `content TEXT NOT NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'`
- `source_ref_type VARCHAR(64) NULL`
- `source_ref_id VARCHAR(255) NULL`
- `created_by VARCHAR(64) NOT NULL DEFAULT 'system'`
- `created_at TIMESTAMP NOT NULL DEFAULT NOW()`

Indexes:

- `(namespace, scope_type, scope_key, created_at DESC)`
- `(event_type, created_at DESC)`
- `(slug_hint)`

### Table 2: `compiled_pages`

Purpose: current materialized view of compiled knowledge.

Columns:

- `id UUID PRIMARY KEY`
- `namespace VARCHAR(255) NOT NULL`
- `scope_type VARCHAR(64) NOT NULL`
- `scope_key VARCHAR(255) NOT NULL`
- `slug VARCHAR(255) NOT NULL`
- `title VARCHAR(255) NOT NULL`
- `summary TEXT NULL`
- `current_revision_id UUID NULL`
- `embedding vector(1536) NULL`
- `freshness_at TIMESTAMP NULL`
- `confidence DECIMAL(5,4) NULL`
- `status VARCHAR(32) NOT NULL DEFAULT 'active'`
- `created_at TIMESTAMP NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMP NOT NULL DEFAULT NOW()`

Indexes:

- unique `(namespace, scope_type, scope_key, slug)`
- IVFFlat or HNSW index on `embedding`
- `(status, freshness_at DESC)`

### Table 3: `compiled_page_revisions`

Purpose: immutable revision history for each compiled page.

Columns:

- `id UUID PRIMARY KEY`
- `page_id UUID NOT NULL REFERENCES compiled_pages(id) ON DELETE CASCADE`
- `revision_number INTEGER NOT NULL`
- `markdown_content TEXT NOT NULL`
- `change_summary TEXT NULL`
- `compiled_from_event_cursor TIMESTAMP NULL`
- `compiled_by VARCHAR(32) NOT NULL`
- `model_name VARCHAR(255) NULL`
- `created_at TIMESTAMP NOT NULL DEFAULT NOW()`

Unique:

- `(page_id, revision_number)`

### Table 4: `compiled_revision_sources`

Purpose: provenance mapping from revision to source events.

Columns:

- `revision_id UUID NOT NULL REFERENCES compiled_page_revisions(id) ON DELETE CASCADE`
- `knowledge_event_id UUID NOT NULL REFERENCES knowledge_events(id) ON DELETE CASCADE`

Unique:

- `(revision_id, knowledge_event_id)`

### Table 5: `page_links`

Purpose: extracted wiki links for graph traversal.

Columns:

- `id UUID PRIMARY KEY`
- `source_page_id UUID NOT NULL REFERENCES compiled_pages(id) ON DELETE CASCADE`
- `target_slug VARCHAR(255) NOT NULL`
- `target_page_id UUID NULL REFERENCES compiled_pages(id) ON DELETE SET NULL`
- `link_text VARCHAR(255) NULL`
- `created_at TIMESTAMP NOT NULL DEFAULT NOW()`

Indexes:

- `(source_page_id)`
- `(target_slug)`

### Table 6: `page_annotations`

Purpose: human comments, suggestions, and approved override notes.

Columns:

- `id UUID PRIMARY KEY`
- `page_id UUID NOT NULL REFERENCES compiled_pages(id) ON DELETE CASCADE`
- `annotation_type VARCHAR(64) NOT NULL`
- `content TEXT NOT NULL`
- `created_by VARCHAR(255) NOT NULL`
- `approved BOOLEAN NOT NULL DEFAULT FALSE`
- `created_at TIMESTAMP NOT NULL DEFAULT NOW()`

---

## Scope and Namespace Rules

Do not use a globally unique topic string.

Every page must be scoped by:

- `namespace`
- `scope_type`
- `scope_key`
- `slug`

Initial namespaces:

- `agent_private`
- `shared_market`

Initial scope types:

- `agent`
- `symbol`
- `strategy`

Initial page slugs:

- `lessons`
- `failure-patterns`
- `market-behavior`
- `execution-notes`

Examples:

- `agent_private / agent / mean_reversion_agent / lessons`
- `shared_market / symbol / BTCUSD / market-behavior`
- `shared_market / symbol / AAPL / execution-notes`

---

## Trigger Policy

Compilation must not fire on every incoming Redis event.

### Allowed phase-1 triggers

1. Deep reflection completion in `TradeReflector._reflect_deep`
2. Generated autopsy text in `AutopsyGenerator.get_or_generate`
3. Shared market observations extracted from deep reflection
4. Explicit operator note or manual recompile request

### Disallowed phase-1 triggers

- Quote streams
- Generic signal events
- Every memory write
- Every journal update

### Batching rules

- Debounce by page key for 2-10 minutes
- Coalesce multiple source events into one compilation pass
- One compiler lock per page key
- DLQ failed compile requests after bounded retries

---

## Compiler Worker

Add a dedicated compiler worker to the trading app.

### New files

- `trading/knowledge/compiler.py`
- `trading/knowledge/models.py`
- `trading/knowledge/store.py`
- `trading/knowledge/link_parser.py`
- `trading/knowledge/prompts.py`
- `trading/knowledge/service.py`
- `trading/api/routes/knowledge.py`

### Update files

- `trading/api/app.py`
- `trading/events/consumer_streams.py`
- `trading/learning/trade_reflector.py`
- `trading/journal/autopsy.py`
- `scripts/init-trading-tables.sql`
- `trading/storage/db.py`

### Compiler responsibilities

1. Load current page revision
2. Load all uncompiled `knowledge_events` for that page
3. Build the maintenance prompt
4. Request a compiled Markdown revision from the LLM
5. Parse wikilinks
6. Write a new immutable revision
7. Update page summary, embedding, freshness, confidence, status
8. Record full provenance

### Maintenance prompt requirements

The compiler prompt must force these behaviors:

- preserve factual uncertainty
- summarize contradictions explicitly
- prefer newer evidence only when the domain is time-sensitive
- keep `[[wikilinks]]` stable
- emit a short change summary
- never invent provenance
- avoid imperative trading instructions unless they are already supported by repeated evidence

---

## Runtime Retrieval Strategy

Phase 1 uses hybrid retrieval, not replacement.

### Current flow

- agent queries raw private/shared memories
- raw journal search may be used for similar trades

### New flow

1. Retrieve 1-3 relevant compiled pages
2. Retrieve fresh raw evidence from memory/journal
3. Return both:
- compiled page as stable prior
- raw items as freshness delta

### Why

Compiled pages are useful for durable understanding.
Raw evidence is still required for freshness and contradiction handling.

---

## API Plan

Add FastAPI routes in `trading/api/routes/knowledge.py`.

### Endpoints

- `GET /api/knowledge/pages`
- `GET /api/knowledge/pages/{page_id}`
- `GET /api/knowledge/pages/{page_id}/revisions`
- `GET /api/knowledge/search?q=...`
- `GET /api/knowledge/graph`
- `POST /api/knowledge/recompile`
- `POST /api/knowledge/pages/{page_id}/annotations`

### Route behavior

- read-only page retrieval in phase 1
- annotations allowed, direct compiled page mutation not allowed
- manual recompiles restricted and rate-limited

---

## Frontend Plan

The current graph page is mocked. Replace it only after page APIs exist.

### New UI rollout

#### Step 1: Read-only page viewer

Files:

- `frontend/src/pages/KnowledgePages.tsx`
- `frontend/src/lib/api/knowledge.ts`

Capabilities:

- render Markdown page
- show freshness
- show confidence
- show provenance event count
- show revision history

#### Step 2: Graph integration

Update:

- `frontend/src/pages/KnowledgeGraph.tsx`

Replace mock data with:

- compiled pages as nodes
- wikilinks as edges
- optional filter by namespace/scope

#### Step 3: Annotation UX

Files:

- `frontend/src/components/knowledge/PageAnnotations.tsx`

Capabilities:

- add annotation
- review approved override notes
- no direct page editing in phase 1

---

## Detailed Task Breakdown

## Phase 1: Storage Foundation

- [ ] Add `knowledge_events`, `compiled_pages`, `compiled_page_revisions`, `compiled_revision_sources`, `page_links`, `page_annotations` to `scripts/init-trading-tables.sql`
- [ ] Add matching SQLite fallback tables to `trading/storage/db.py`
- [ ] Add storage models and repository methods in `trading/knowledge/models.py` and `trading/knowledge/store.py`
- [ ] Add a small schema smoke test for both PostgreSQL and SQLite code paths

## Phase 2: Event Production

- [ ] Emit `knowledge_events` from `TradeReflector._reflect_deep`
- [ ] Emit `knowledge_events` from `AutopsyGenerator.get_or_generate`
- [ ] Add helper service for event writes so emitters stay small
- [ ] Define page routing rules from event -> page key

## Phase 3: Compiler Worker

- [ ] Add compile request event type, consumer registration, and per-page debounce
- [ ] Implement `KnowledgeCompiler`
- [ ] Implement link extraction and persistence
- [ ] Implement revision write path with provenance
- [ ] Add retry and DLQ behavior

## Phase 4: Runtime Read Path

- [ ] Add `KnowledgeService` to retrieve pages by scope
- [ ] Add a helper that returns `compiled_pages + fresh raw evidence`
- [ ] Wire one agent path to prefer compiled context
- [ ] Keep raw-only fallback if no page exists

## Phase 5: API and UI

- [ ] Add FastAPI routes for pages, revisions, graph, annotations
- [ ] Add frontend page viewer
- [ ] Replace mock graph data with real graph API
- [ ] Add annotation UI

## Phase 6: Validation

- [ ] Verify every revision has source events
- [ ] Verify compile batching limits LLM churn
- [ ] Verify stale pages do not block raw evidence retrieval
- [ ] Run one offline evaluation comparing:
  - raw-only context
  - compiled + raw context
- [ ] Confirm no regression in autopsy and journal flows

---

## File-Level Execution Plan

### Database and storage

- `scripts/init-trading-tables.sql`
- `trading/storage/db.py`
- `trading/knowledge/models.py`
- `trading/knowledge/store.py`

### Event production

- `trading/learning/trade_reflector.py`
- `trading/journal/autopsy.py`
- `trading/knowledge/service.py`

### Compiler and worker

- `trading/knowledge/compiler.py`
- `trading/knowledge/link_parser.py`
- `trading/knowledge/prompts.py`
- `trading/api/app.py`
- `trading/events/consumer_streams.py`

### Runtime retrieval

- `trading/api/routes/memory.py`
- `trading/journal/manager.py`
- `trading/learning/memory_client.py`

### API and frontend

- `trading/api/routes/knowledge.py`
- `frontend/src/lib/api/knowledge.ts`
- `frontend/src/pages/KnowledgePages.tsx`
- `frontend/src/pages/KnowledgeGraph.tsx`
- `frontend/src/components/knowledge/PageAnnotations.tsx`

---

## Acceptance Criteria

Phase 1 is complete when:

1. A closed trade can produce one or more `knowledge_events`.
2. Those events compile into a revisioned Markdown page.
3. The page stores provenance back to source events.
4. Agents can retrieve compiled page content plus fresh raw evidence.
5. The frontend can display the page and its revisions.

---

## Risks and Mitigations

### Risk: LLM churn and queue pressure

Mitigation:

- debounce
- page-level locking
- bounded retries
- explicit trigger classes only

### Risk: stale compiled pages

Mitigation:

- freshness timestamps
- status flags
- raw evidence always included in runtime path

### Risk: human edits become silent trading policy

Mitigation:

- annotations and overrides stored separately
- no direct mutation of machine revisions in phase 1

### Risk: duplicate knowledge systems

Mitigation:

- reuse reflection, autopsy, and journal seams
- do not replace existing search paths until evaluated

---

## Recommended First Slice

Implement only this vertical slice first:

- `knowledge_events`
- `compiled_pages`
- `compiled_page_revisions`
- event emission from `TradeReflector._reflect_deep`
- one compiler page type:
  - `agent_private / agent / {agent_name} / lessons`
- one read endpoint:
  - `GET /api/knowledge/pages/{page_id}`

If that slice proves useful, expand to shared market pages and graph rendering.

---

## Commit Strategy

This plan should land as a documentation-only commit first.

Suggested commit message:

`docs(plan): add compiled knowledge layer implementation plan`
