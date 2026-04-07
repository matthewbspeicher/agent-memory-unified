# TP-015: Vector Memory Migration — Hybrid Fallback — Status

**Current Step:** Step 0: Preflight
**Status:** 🔵 In Progress
**Last Updated:** 2026-04-07
**Review Level:** 1
**Review Counter:** 0
**Iteration:** 0
**Size:** M

---

### Step 0: Preflight
**Status:** 🔵 In Progress

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Read existing memory config in config.py
- [ ] Check if pgvector extension is available in trading PostgreSQL
- [ ] Verify HNSW index already exists for journal entries

---

### Step 1: Create Local Memory Store
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Create `trading/storage/memory.py` with local MemoryStore class
- [ ] Add pgvector column for embedding storage
- [ ] Implement store, get, search methods with cosine similarity

---

### Step 2: Enhance Memory Client with Hybrid Fallback
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Wrap TradingMemoryClient to try remembr.dev first
- [ ] On failure, fall back to local MemoryStore
- [ ] Add health check to verify local pgvector connectivity

---

### Step 3: Add Local Config
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Add local memory config in config.py (enable/disable, pg connection)
- [ ] Wire local memory store in app.py

---

### Step 4: Write Tests
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Test local MemoryStore CRUD operations
- [ ] Test hybrid fallback when remote unavailable
- [ ] Test semantic search with pgvector

---

### Step 5: Testing & Verification
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Local memory store works
- [ ] Hybrid mode fails over correctly
- [ ] Existing tests still pass

---

### Step 6: Documentation & Delivery
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Update CLAUDE.md with local memory option
- [ ] Log discoveries

---

## Reviews
| # | Type | Step | Verdict | File |
|---|------|------|---------|------|

## Discoveries
| Discovery | Disposition | Location |
|-----------|-------------|----------|

## Execution Log
| Timestamp | Action | Outcome |
|-----------|--------|---------|
| 2026-04-07 | Task staged | PROMPT.md created |
| 2026-04-07 | Step 0 | Beginning preflight analysis |

## Blockers
*None*

## Notes
*Starting preflight analysis - checking existing memory config and pgvector availability*
