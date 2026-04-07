# ADR-001: Hybrid Memory Architecture

**Status**: accepted

**Date**: 2026-04-07
**Deciders**: Development Team

---

## Context

The trading engine previously relied solely on an external service (remembr.dev) for agent memory. We needed resilience when this service is unavailable.

## Decision

Implement a hybrid memory architecture:
- **Primary**: remembr.dev (external service) - remains the default
- **Fallback**: Local SQLite store with LocalMemoryStore class

The HybridTradingMemoryClient attempts remote first, falls back to local on failure.

## Consequences

### Positive
- Service resilience: operations continue when remembr.dev is down
- No external dependency for basic operations
- Easy to test locally

### Negative
- Two stores to maintain
- Local search uses keyword matching (not semantic) - full semantic search requires embeddings

### Neutral
- Local store uses SQLite (simpler than PostgreSQL for local dev)
- Both stores support the same API surface

---

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| Self-host pgvector | Full semantic search | More infra, pgvector setup |
| Only remembr.dev | Simpler | Single point of failure |

---

## Notes

- See `trading/storage/memory.py` for LocalMemoryStore implementation
- See `trading/learning/memory_client.py` for HybridTradingMemoryClient
- Config via `STA_LOCAL_MEMORY_ENABLED` (disabled by default)
