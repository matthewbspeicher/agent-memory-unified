# TP-015: Vector Memory Migration — Hybrid Fallback

**Created:** 2026-04-07
**Size:** M

## Review Level: 1 (Plan Only)

**Assessment:** Feature extension with fallback. Low risk - adds resilience without removing existing functionality.
**Score:** 2/8 — Blast radius: 1, Pattern novelty: 1, Security: 1, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-015-vector-memory-hybrid/
```

## Mission

Add local pgvector fallback to the trading engine's memory system. When remembr.dev is unavailable, operations fail over to local PostgreSQL with pgvector.

## Dependencies

- TP-013 (Laravel API Decision) — defines the migration path
- Existing memory infrastructure (TradingMemoryClient, remembr.dev)

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `trading/config.py` — config for memory/remembr settings
- `trading/learning/memory_client.py` — existing client wrapper
- `trading/api/routes/memory.py` — memory API routes

## Environment

- **Workspace:** `trading/`
- **Services required:** PostgreSQL with pgvector extension

## File Scope

- `trading/storage/memory.py` (new) — local memory store with pgvector
- `trading/learning/memory_client.py` (enhanced) — add hybrid wrapper
- `trading/config.py` (enhanced) — add local memory config

## Steps

### Step 0: Preflight
- [ ] Read existing memory config in config.py
- [ ] Check if pgvector extension is available in trading PostgreSQL
- [ ] Verify HNSW index already exists for journal entries

### Step 1: Create Local Memory Store
- [ ] Create `trading/storage/memory.py` with local MemoryStore class
- [ ] Add pgvector column for embedding storage
- [ ] Implement store, get, search methods with cosine similarity

### Step 2: Enhance Memory Client with Hybrid Fallback
- [ ] Wrap TradingMemoryClient to try remembr.dev first
- [ ] On failure, fall back to local MemoryStore
- [ ] Add health check to verify local pgvector connectivity

### Step 3: Add Local Config
- [ ] Add local memory config in config.py (enable/disable, pg connection)
- [ ] Wire local memory store in app.py

### Step 4: Write Tests
- [ ] Test local MemoryStore CRUD operations
- [ ] Test hybrid fallback when remote unavailable
- [ ] Test semantic search with pgvector

### Step 5: Testing & Verification
- [ ] Local memory store works
- [ ] Hybrid mode fails over correctly
- [ ] Existing tests still pass

### Step 6: Documentation & Delivery
- [ ] Update CLAUDE.md with local memory option
- [ ] Log discoveries

## Documentation Requirements
**Must Update:** `CLAUDE.md` — document hybrid memory architecture

## Completion Criteria
- [ ] remembr.dev remains primary memory backend
- [ ] Local pgvector fallback activates when remote unavailable
- [ ] Both backends support semantic search

## Git Commit Convention
- `feat(TP-015): complete Step N — description`

## Do NOT
- Remove remembr.dev integration
- Migrate all memories from remembr.dev (only add local capability)
- Add new npm dependencies
