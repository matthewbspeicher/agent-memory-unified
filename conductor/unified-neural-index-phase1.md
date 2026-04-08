# Phase 1: Unified Neural Index Plan

## Objective
Implement a local embedding architecture for Agent Memory Commons. This adds pgvector support to the unified database, establishes a dedicated background worker in the Python `trading/` service to generate local embeddings (`all-MiniLM-L6-v2`), and uses Redis Streams for auto-indexing new memories.

## Key Files & Context
- **Laravel Migration:** New file in `api/database/migrations/`
- **Laravel Listener:** `api/app/Listeners/PublishMemoryToStream.php`
- **Laravel Event:** `api/app/Events/MemoryCreated.php`
- **Python Worker:** `trading/scripts/consume_memories.py`

## Implementation Steps

### 1. Database Migration (Laravel)
- Create migration `add_local_embedding_to_memories_table`.
- Add a `local_embedding` column of type `vector(384)` to the `memories` table to support `all-MiniLM-L6-v2`.
- Add an IVFFlat index on the `local_embedding` column using `vector_cosine_ops`.

### 2. Redis Stream Publisher (Laravel)
- Map `PublishMemoryToStream` listener to memory creation events.
- Publish a payload to `memories_indexing_stream` including: `memory_id`, `agent_id`, and `content`.

### 3. Local Embedding Service (Python Background Worker)
- Create `trading/scripts/consume_memories.py`.
- Initialize `SentenceTransformer('all-MiniLM-L6-v2')`.
- Implement `strip_private_content` regex (`<private>.*?</private>`) to redact sensitive information.
- Consume messages from `memories_indexing_stream` using `redis`.
- Generate the 384-dimensional embedding vector.
- Update `local_embedding` in PostgreSQL `memories` table via `asyncpg`.
- Acknowledge the Redis Stream message.

## Verification & Testing
1. **Migration Test:** Run `php artisan migrate` and verify the `local_embedding` column exists with the correct 384-dimension limit.
2. **Stream Publishing:** Create a test memory via Laravel Tinker and verify the payload in `memories_indexing_stream`.
3. **End-to-End Pipeline:** 
   - Start `python3 trading/scripts/consume_memories.py`.
   - Create a memory with `<private>secret</private>` tags.
   - Verify the Python worker processes the message, redacts the secret, and updates the DB.