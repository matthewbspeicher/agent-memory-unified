# ADR-0005: API Boundaries and Domain Ownership (Laravel vs FastAPI)

**Status**: superseded by [ADR-0006](0006-laravel-removal.md)

**Date**: 2026-04-08
**Deciders**: Architecture review session

> ⚠️ **Superseded by ADR-0006 (Laravel removal, 2026-04-09).**
> This ADR assumes a coexisting Laravel + FastAPI two-backend world. Laravel was removed entirely the day after this was written. The route prefix conventions for `/engine/v1/*` and `/api/*` against the FastAPI trading engine remain accurate, but every reference to "Laravel" in this document describes a system that no longer exists in this repository. Preserved for historical context.

---

## Context

The Agent Memory Commons platform consisted of a Laravel backend (Memory API) and a Python/FastAPI trading engine. As the system grew, the boundaries between these two services became blurred, leading to confusion regarding domain ownership, authentication, and API routing. We needed to establish clear architectural boundaries to ensure maintainability, scalability, and independent deployment of these services. Furthermore, the Python codebase relied on ad-hoc script execution at the time, which hindered testing and modularity.

## Decision

Establish strict API boundaries and domain ownership between the Laravel and FastAPI services, treating them as distinct APIs from the frontend's perspective.

### 1. API Boundary & Route Prefixes

To avoid a faux unified boundary and clearly delineate the services, distinct route prefixes:

- **Laravel (Product API):** All routes prefixed with `/api/v1/`
- **FastAPI (Trading/Agent Engine):** All routes prefixed with `/engine/v1/`

The frontend would route requests to the appropriate service based on these prefixes (e.g., via the Nginx reverse proxy gateway).

### 2. Domain Ownership

Strictly divide domain responsibilities based on target audience (Human vs. Agent):

- **Laravel (Human-Facing):** UI data serving, 3D Knowledge Graph, Auth/Authz, Workspaces and Tasks, general CRUD for user-facing entities
- **FastAPI (Agent-Facing):** Agent Memory and LLM ingestion, Daily Compilers and Strategy Indexing, Semantic Search (pgvector), Competition and Bittensor network integration, Trade execution and monitoring, Websocket/SSE streaming, Background Workers (`DailyTradeCompiler`, `FidelityFileWatcher`, `BittensorScheduler` isolated in `api/startup/workers.py`)

### 3. Authentication Model

- **Laravel as Primary Auth Server:** Handles all user authentication, issues JWTs / API keys
- **FastAPI Validation:** Validates Laravel-issued JWTs/keys for incoming requests via shared secret (or public key for asymmetric encryption)
- **Service-to-Service Auth:** Shared secret or dedicated service tokens for internal Laravel ↔ FastAPI communication

### 4. Python Packaging & Dependency Management

- **Single Source of Truth:** `uv` and `pyproject.toml` are the absolute single source of truth. `requirements.txt` and `requirements-test.txt` are deprecated.
- **Real Package Structure:** Restructure the Python service as a standard installable Python package (`from trading.core import execute_trade`)
- **Deprecation of Ad-hoc Scripts:** Executing standalone Python scripts or mutating `sys.path` (e.g. inside `dependencies.py`) is forbidden

## Consequences

### Positive

- **Clear Separation of Concerns:** Developers know exactly where a new feature belongs based on whether it is human-facing or agent-facing
- **Independent Scaling:** Heavy computational FastAPI workloads can be scaled independently from standard Laravel web traffic
- **Simplified Frontend Logic:** Frontend can route requests based on URL prefix
- **Improved Python Codebase:** uv-based packaging leads to better organization, easier testing, instant dependency resolution
- **Unified Auth:** Single source of truth for user authentication

### Negative

- **Initial Refactoring Overhead:** Moving existing routes and logic to adhere to new boundaries required significant effort
- **Cross-Service Communication:** Features needing data from both domains require cross-service API calls or shared database/event bus, adding complexity vs a monolith
- **Shared Secret Management:** JWT secret must be securely distributed and synchronized between both services

### Neutral

- The Python packaging recommendations (uv as single source of truth, real package structure, no `sys.path` mutation) survived the Laravel removal and remain in force as of ADR-0006

---

## Alternatives Considered

> Original ADR did not enumerate alternatives. The implicit alternative was the status quo (blurred boundaries, ad-hoc routing, fragmented dependency management), which the decision rejected.

---

## Notes

- **Superseded by:** [ADR-0006: Laravel removal](0006-laravel-removal.md) — the Laravel half of this two-API world was removed entirely on 2026-04-09. The `/engine/v1/*` prefix and FastAPI domain ownership are preserved; the `/api/v1/*` Laravel half is gone.
- The Python packaging decisions (sections 4) remain in force.
