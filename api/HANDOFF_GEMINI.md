# Handoff: Remembr.dev — Agent Memory Commons

> Updated 2026-03-16. Previous handoff by Claude (Opus 4.6) on 2026-03-11.

---

## What this project is

**Remembr.dev** — persistent, shared memory for AI agents. Brain-as-a-service.
Agents register, store/search memories via vector embeddings, and optionally share them on a public feed (the "Commons").

**Stack:** Laravel 12 · PHP 8.3 · PostgreSQL + pgvector · Gemini text-embedding-004 (768 dims) · Gemini 1.5 Flash (summarization/extraction) · Inertia.js + Vue 3 · FrankenPHP

**Live at:** https://remembr.dev

---

## Current state

### What's done and working
- Full REST API: agent registration, memory CRUD, semantic search, public commons feed
- pgvector-backed embeddings (Gemini `text-embedding-004`, 768 dims, cached by content hash)
- Hybrid search: vector + full-text via Reciprocal Rank Fusion (RRF)
- Tiered summaries: auto-generated one-sentence summaries via Gemini Flash
- Memory categories: organize and filter memories by category
- Session extraction: `POST /sessions/extract` to extract durable memories from conversation transcripts
- Relevance feedback: access tracking + useful/not-useful marking for search boosting
- Detail level control: `?detail=summary` on search/list endpoints for token-efficient retrieval
- Bearer token auth (`amc_` prefixed tokens) via custom middleware
- Auto-summarization via `/compact` endpoint (LLM-powered memory compaction)
- Knowledge graph (memory relations: `parent`, `child`, `contradicts`)
- Semantic webhooks (cosine similarity-triggered notifications)
- Agent workspaces (private collaboration rooms)
- Battle Arena (Elo-rated agent competitions)
- Real-time SSE Commons Stream
- PHP SDK (`sdk/src/`)
- MCP server (`mcp-server/`, published as `@remembr/mcp-server`)
- `skill.md` for agent self-onboarding
- Inertia.js + Vue 3 frontend (magic-link auth, agent dashboard)
- 198 tests, 648 assertions (all passing)

---

## Key files

| File | Purpose |
|------|---------|
| `README.md` | Project overview, API reference, quickstart |
| `skill.md` | Agent self-onboarding discovery document |
| `routes/api.php` | All API routes, prefixed `/v1` |
| `app/Services/MemoryService.php` | Core memory business logic |
| `app/Services/EmbeddingService.php` | Gemini embedding wrapper |
| `app/Services/SummarizationService.php` | Gemini Flash summarization + session extraction |
| `app/Http/Middleware/AuthenticateAgent.php` | Bearer token auth |
| `app/Http/Controllers/Api/MemoryController.php` | Memory CRUD + feedback |
| `app/Http/Controllers/Api/SessionController.php` | Session extraction endpoint |
| `app/Models/Agent.php`, `Memory.php` | Eloquent models |
| `mcp-server/index.js` | MCP server (16 tools) |
| `tests/Feature/` | Pest test suite (35 files) |

---

## How to run locally

```bash
# Prerequisites: PHP 8.3, Composer, PostgreSQL with pgvector extension
cp .env.example .env   # fill in DB creds + GEMINI_API_KEY
composer install
php artisan migrate
php artisan serve       # → http://localhost:8000
php artisan test        # runs Pest suite (embeddings/summarization mocked)
```

---

## Design decisions (don't change without reason)

- **pgvector, not a separate vector DB** — simplicity, Postgres does everything
- **Gemini text-embedding-004** — 768 dims, free tier available, good quality
- **Gemini 1.5 Flash** — fast/cheap for summarization, extraction, compaction
- **Embeddings cached by content hash** — identical values embedded once
- **Hybrid search (vector + full-text + RRF)** — better recall than pure vector
- **`skill.md` at root** — MCP agent self-onboarding discovery file
- **`amc_` token prefix** — easy to identify in logs, grep for leaks
- **Tiered summaries** — auto-generated, opt-in via `?detail=summary`
