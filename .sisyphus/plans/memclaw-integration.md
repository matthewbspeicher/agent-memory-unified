# Plan: MemClaw-Inspired Memory Architecture Upgrade

## TL;DR

> **Quick Summary**: Upgrade the trading engine's memory system with MemClaw's proven patterns — structured memory types with decay, status lifecycle, visibility scopes (agent/team/org), and search tuning parameters.
> 
> **Deliverables**:
> - Updated JSON schema with 13 memory types + 8 statuses
> - LocalMemoryStore schema migration
> - Search tuning API (`/engine/v1/memory/tune`)
> - Status transition endpoints
> - Visibility scope filtering
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Schema → LocalStore → API routes → Tests

---

## Context

### Original Request
Learn from MemClaw (https://memclaw.net/for-agents) and incorporate its patterns into the agent-memory-unified project.

### Research Findings
MemClaw provides:
- **13 Memory Types**: fact, episode, decision, preference, task, semantic, intention, plan, commitment, action, outcome, cancellation, rule — each with decay windows
- **8 Statuses**: active → pending → confirmed/cancelled → outdated/archived/conflicted — with lifecycle transitions
- **3 Visibility Scopes**: scope_agent, scope_team, scope_org — cross-agent sharing with trust levels
- **Search Tuning**: top_k, min_similarity, fts_weight, freshness boost, graph traversal
- **Auto-enrichment**: LLM infers metadata from content
- **Knowledge Graph**: Entity extraction
- **Contradiction Detection**: Auto-detects conflicts

### Current State
- `LocalMemoryStore` has: id, agent_id, key, value, visibility (private/public), memory_type (ad-hoc), importance (1-10), tags, created_at
- No status field, no decay logic, no search tuning, 2 visibility levels only

---

## Work Objectives

### Core Objective
Upgrade memory system with MemClaw's proven taxonomy and lifecycle patterns.

### Concrete Deliverables
1. Updated `memory.schema.json` with 13 memory types, 8 statuses, 3 visibility scopes
2. LocalMemoryStore schema migration (add status, weight, visibility_scope, decay_days)
3. New `/engine/v1/memory/tune` endpoint for search tuning
4. New `/engine/v1/memory/{id}/transition` endpoint for status changes
5. Updated `/engine/v1/memory/search` with visibility_scope filter
6. Decay scheduler (mark memories outdated based on type + days)

### Definition of Done
- [ ] Schema updated and types regenerated
- [ ] LocalMemoryStore migrates existing data
- [ ] All 4 new endpoints working
- [ ] Unit tests pass for new functionality

### Must Have
- Backward compatibility with existing memory data
- Default decay windows per memory type (matching MemClaw)
- Search tuning parameters persisted per-agent

### Must NOT Have
- Breaking changes to existing API contracts
- Remove legacy "private/public" visibility (map to scope_agent/scope_team)

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: Tests-after
- **Framework**: pytest

### QA Policy
Every task includes agent-executed QA scenarios.

---

## Execution Strategy

### Wave 1 (Schema + Core)
- Task 1: Update memory.schema.json
- Task 2: Regenerate Python/TypeScript types
- Task 3: Update LocalMemoryStore model + migration

### Wave 2 (API + Logic)
- Task 4: Add tune endpoint with params storage
- Task 5: Add status transition endpoint
- Task 6: Update search with visibility scopes + tuning
- Task 7: Add decay scheduler logic
- Task 8: Add unit tests

---

## TODOs

- [ ] 1. Update memory.schema.json with 13 types, 8 statuses, 3 scopes

  **What to do**:
  - Add `memory_type` enum with all 13 MemClaw types
  - Add `status` enum with all 8 MemClaw statuses  
  - Add `visibility_scope` enum: scope_agent, scope_team, scope_org
  - Add `weight` field (0-1) for importance
  - Add `decay_days` computed field based on type
  - Keep legacy `visibility` field for backward compat

  **References**:
  - `shared/types/schemas/memory.schema.json` - current schema
  - `https://memclaw.net/for-agents` - MemClaw reference

  **Acceptance Criteria**:
  - [ ] Schema validates
  - [ ] All 13 types present in enum
  - [ ] All 8 statuses present in enum

- [ ] 2. Regenerate Python and TypeScript types

  **What to do**:
  - Run `./shared/types/scripts/generate-types.sh`
  - Verify generated files have new fields

  **References**:
  - `shared/types/scripts/generate-types.sh` - generation script

  **Acceptance Criteria**:
  - [ ] Python types have new enums
  - [ ] TypeScript types have new enums
  - [ ] No import errors

- [ ] 3. Update LocalMemoryStore with new schema fields

  **What to do**:
  - Add `status` column with default "active"
  - Add `weight` column (Float, default 0.5)  
  - Add `visibility_scope` column (TEXT, default "scope_agent")
  - Add `decay_days` computed property based on memory_type
  - Add idempotent migration for existing databases
  - Update `_row_to_record` to handle new fields

  **References**:
  - `trading/storage/memory.py` - LocalMemoryStore implementation

  **Acceptance Criteria**:
  - [ ] New columns exist in SQLite
  - [ ] Existing data preserved (status defaults to active)
  - [ ] get() returns new fields

- [ ] 4. Add /engine/v1/memory/tune endpoint

  **What to do**:
  - New POST endpoint accepting: top_k, min_similarity, fts_weight, freshness_floor, freshness_decay_days, graph_max_hops, similarity_blend
  - Store tuning params in memory registry (in-memory per agent)
  - GET endpoint to retrieve current tuning
  - Apply tuning to search queries

  **References**:
  - `trading/api/routes/memory.py` - existing routes
  - `trading/api/services/memory_registry.py` - registry service

  **Acceptance Criteria**:
  - [ ] POST /tune returns 200
  - [ ] GET /tune returns stored params
  - [ ] Search uses tuned params

- [ ] 5. Add /engine/v1/memory/{id}/transition endpoint

  **What to do**:
  - New POST endpoint: path param memory_id, body {status}
  - Validate status transitions (active→pending→confirmed allowed, etc.)
  - Update LocalMemoryStore record
  - Return updated memory

  **References**:
  - MemClaw status lifecycle: pending→confirmed, active→outdated, etc.

  **Acceptance Criteria**:
  - [ ] Valid transition returns 200
  - [ ] Invalid transition returns 400
  - [ ] Status updated in database

- [ ] 6. Update search with visibility scopes + tuning

  **What to do**:
  - Add `visibility_scope` filter to search params
  - Apply stored tuning params to search query
  - Add `memory_type_filter` and `status_filter`
  - Implement freshness boosting based on decay

  **References**:
  - `trading/storage/memory.py:search()` - current search

  **Acceptance Criteria**:
  - [ ] Filter by scope_team returns team-visible memories
  - [ ] Filter by memory_type works
  - [ ] Filter by status works

- [ ] 7. Add decay scheduler logic

  **What to do**:
  - Create `decay_scheduler.py` module
  - Function to find memories past decay threshold by type
  - Update their status to "outdated"
  - Add cron-style task to run periodically
  - Config: STA_MEMORY_DECAY_ENABLED (default false)

  **References**:
  - MemClaw decay table: task=30d, episode=45d, fact=120d, etc.

  **Acceptance Criteria**:
  - [ ] Scheduler marks old memories outdated
  - [ ] Config enables/disables

- [ ] 8. Add unit tests for new functionality

  **What to do**:
  - Test memory_type enum validation
  - Test status transition validation
  - Test visibility scope filtering
  - Test tune endpoint
  - Test decay logic

  **References**:
  - `trading/tests/unit/test_storage/test_memory.py` - existing tests

  **Acceptance Criteria**:
  - [ ] All new tests pass
  - [ ] Existing tests still pass

---

## Final Verification Wave

- [ ] F1. Schema validation — verify JSON schema is valid
- [ ] F2. Type generation — verify Python/TS types compile
- [ ] F3. API smoke test — hit new endpoints with curl
- [ ] F4. Test suite — pytest passes

---

## Commit Strategy

- `feat(memory): add MemClaw-style memory types and status lifecycle`
- Files: shared/types/schemas/memory.schema.json, trading/storage/memory.py, trading/api/routes/memory.py, trading/tests/...