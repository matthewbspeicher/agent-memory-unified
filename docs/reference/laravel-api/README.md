# Laravel API Reference (Deprecated)

**Status:** Deprecated (TP-013). Code removed 2026-04-09.
**Purpose:** Preserve high-value vector memory logic for future migration to FastAPI.

## High-Value Code to Preserve

### 1. EmbeddingService.php

Key patterns for vector embedding:
- **Provider:** Gemini (`gemini-embedding-2-preview`) with Bedrock fallback
- **Dimensions:** 3072 → truncated to 1536 via Matryoshka slicing
- **Caching:** Content hash (xxh128) with 7-day TTL
- **Batch API:** Uses `batchEmbedContents` endpoint for efficiency

**Relevant for:** Porting to Python when adding semantic search to trading engine.

### 2. MemorySearchService.php

Key patterns for hybrid search:
- **Vector search:** pgvector cosine similarity via `semanticSearch()` scope
- **Keyword search:** PostgreSQL FTS via `keywordSearch()` scope
- **Reciprocal Rank Fusion (RRF):** `k=60`, standard formula `1/(k+rank)`
- **Augmented ranking:** Time decay `e^(-0.01 * days_old)`, importance multiplier, confidence multiplier, relevance multiplier (useful_ratio)

**Relevant for:** Upgrading trading engine's memory search from keyword-only to hybrid vector+keyword.

## Database Schema

The Laravel migrations define 44 tables. Key ones for vector memory:

- `memories` — core table with `embedding vector(1536)` column + IVFFlat index
- `agents` — agent registry with token auth
- `memory_shares` — cross-agent memory sharing
- `memory_tags` — many-to-many tag association

**Note:** Schema is captured in `scripts/init-trading-tables.sql`.

## Migration Path (2-3 days)

When ready to add vector memory to FastAPI:

1. **Python EmbeddingService:**
   - Use `google-generativeai` SDK for Gemini embeddings
   - Add Bedrock fallback via `boto3`
   - Implement content hash caching in Redis

2. **SQLAlchemy Memory Model:**
   - Add `Vector` column type from `sqlalchemy-vector`
   - Create IVFFlat or HNSW index for cosine similarity
   - Implement `semantic_search()` query method

3. **Hybrid Search:**
   - Vector: pgvector `<=>` operator
   - Keyword: PostgreSQL `to_tsvector` + `plainto_tsquery`
   - RRF fusion in Python (same formula as Laravel)
   - Augmented ranking with time decay, weight, confidence

## What NOT to Port

- Arena/Competition system — unused
- Workspaces/Presence — no users
- Achievements/Badges — no users
- Billing (Stripe) — not active
- JWT auth pattern — FastAPI has its own
