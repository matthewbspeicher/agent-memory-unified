# ADR-0006: Replace Laravel API with FastAPI

**Status**: accepted

**Date**: 2026-04-09
**Deciders**: Claude, Gemini, User (cleanup session)

---

## Context

The project historically used a Laravel PHP API (`api/`) alongside the Python FastAPI trading engine (`trading/`). This dual-backend setup, originally documented in ADR-0004 (unified API surface) and ADR-0005 (API boundaries and domain ownership), created ongoing friction:

- Two codebases to maintain in two languages (PHP + Python)
- Inconsistent API patterns and authentication models
- Database confusion: Laravel tables coexisting with Python tables in the same Postgres instance
- Additional Docker service and dependency overhead
- Laravel had drifted into a legacy artifact — it was no longer running in dev or production by the time of this decision

The full feature inventory and migration analysis live in `taskplane-tasks/TP-013-laravel-api-decision/DECISION.md`.

## Decision

Remove the Laravel API entirely. All backend functionality now runs through the FastAPI trading engine on port 8080. Vector memory patterns from the Laravel codebase are preserved as reference under `docs/reference/laravel-api/` for future migration into FastAPI when needed.

This decision **supersedes ADR-0004 and ADR-0005**, both of which assumed a coexisting two-backend architecture (`/api/v1/*` Laravel + `/engine/v1/*` FastAPI).

## Consequences

### Positive

- Single language (Python) for all backend logic
- All routes consolidated under `trading/api/app.py` and `trading/api/routes/`
- Eliminates 46 unused Laravel-owned database tables
- Reduces `docker-compose.yml` complexity (removed laravel and laravel-octane services)
- Simpler mental model for new contributors
- Frontend transport layer simplified to a single `tradingApi` axios instance against FastAPI

### Negative

- Vector memory CRUD that lived in Laravel must be reimplemented in FastAPI when needed (currently parked under `docs/reference/laravel-api/`)
- Knowledge graph, agent registration, workspaces, arena/competition, achievements — all Laravel-owned features — were dropped or must be rebuilt in Python
- Loss of Laravel's mature auth/middleware ecosystem; FastAPI has thinner equivalents
- Any external consumer pointed at `/api/v1/*` is broken by this change

### Neutral

- 44 trading tables recreated in PostgreSQL via `scripts/init-trading-tables.sql`
- The two-API boundary in ADR-0004/0005 collapses to a single API; route prefix conventions in `/engine/v1/*` and `/api/*` for the FastAPI trading engine remain valid (see CLAUDE.md "Working Boundaries" — Bittensor uses `/engine/v1/bittensor/`)
- pgvector remains in use for semantic search, now owned entirely by Python

---

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| Keep Laravel as Memory API only | Preserves mature CRUD code | Two languages, two test suites, two deploy paths for one product |
| Port Laravel features incrementally before removal | No feature loss | Unknown timeline; Laravel was already not running, so blocking removal on ports was not justified |
| Rewrite Laravel features in Node | Familiar to some contributors | Adds a third language to the stack |
| **Remove Laravel and re-port on demand (chosen)** | Smallest immediate diff; defers cost to when features are actually needed | Vector memory CRUD currently absent from the running system |

---

## Notes

- Original decision document with full feature inventory: `taskplane-tasks/TP-013-laravel-api-decision/DECISION.md`
- Reference patterns preserved at: `docs/reference/laravel-api/`
- Supersedes: ADR-0004 (unified-api-surface), ADR-0005 (api-boundaries-and-domain-ownership)
- See CLAUDE.md "Laravel API Status (TP-013 Decision)" section for the operational summary
