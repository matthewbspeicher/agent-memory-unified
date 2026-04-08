# ADR: API Boundaries and Domain Ownership (Laravel vs FastAPI)

## Status
Accepted

## Context
Our Agent Memory Commons platform consists of a Laravel backend (Memory API) and a Python/FastAPI trading engine. As the system has grown, the boundaries between these two services have become blurred, leading to confusion regarding domain ownership, authentication, and API routing. We need to establish clear architectural boundaries to ensure maintainability, scalability, and independent deployment of these services. Furthermore, the Python codebase currently relies on ad-hoc script execution, which hinders testing and modularity.

## Decision

We have decided to establish strict API boundaries and domain ownership between the Laravel and FastAPI services, treating them as distinct APIs from the frontend's perspective.

### 1. API Boundary & Route Prefixes
To avoid a faux unified boundary and clearly delineate the services, we will use distinct route prefixes:
*   **Laravel (Product API):** All routes will be prefixed with `/api/v1/`.
*   **FastAPI (Trading/Agent Engine):** All routes will be prefixed with `/engine/v1/`.
The frontend will be configured to route requests to the appropriate service based on these prefixes (e.g., via the Nginx reverse proxy gateway).

### 2. Domain Ownership
We are strictly dividing domain responsibilities based on the target audience (Human vs. Agent):
*   **Laravel (Human-Facing):** Owns all components related to user interaction and general application state. This includes:
    *   User Interface (UI) data serving
    *   3D Knowledge Graph data
    *   Authentication and Authorization
    *   Workspaces and Tasks management
    *   General CRUD operations for user-facing entities
*   **FastAPI (Agent-Facing):** Owns all components related to AI agents, trading, and heavy computational tasks. This includes:
    *   Agent Memory and LLM ingestion
    *   Daily Compilers and Strategy Indexing
    *   Semantic Search (pgvector integration)
    *   Competition and Bittensor network integration
    *   Trade execution and monitoring
    *   Websocket/SSE streaming for real-time agent/trading updates
    *   Background Workers (e.g. `DailyTradeCompiler`, `FidelityFileWatcher`, `BittensorScheduler` isolated in `api/startup/workers.py`)

### 3. Authentication Model
To maintain a unified security posture while allowing independent operation:
*   **Laravel as Primary Auth Server:** Laravel will handle all user authentication and issue JSON Web Tokens (JWTs) or API keys.
*   **FastAPI Validation:** FastAPI will validate these JWTs/keys for incoming requests. This will be achieved by sharing the JWT secret (or public key, if using asymmetric encryption) between the Laravel and FastAPI environments. FastAPI will not issue its own tokens for users but will trust the tokens issued by Laravel.
*   **Service-to-Service Auth:** For internal communication between Laravel and FastAPI (if necessary), a shared secret or dedicated service tokens will be used.

### 4. Python Packaging & Dependency Management
To improve the maintainability and testability of the Python trading engine:
*   **Single Source of Truth:** `uv` and `pyproject.toml` are the absolute single source of truth. `requirements.txt` and `requirements-test.txt` are deprecated.
*   **Real Package Structure:** The Python service will be restructured and configured as a standard, installable Python package (`from trading.core import execute_trade`).
*   **Deprecation of Ad-hoc Scripts:** Executing standalone Python scripts or mutating `sys.path` (e.g. inside `dependencies.py`) is forbidden.

## Consequences

### Positive
*   **Clear Separation of Concerns:** Developers will know exactly where a new feature belongs based on whether it is human-facing or agent-facing.
*   **Independent Scaling:** The heavy computational workloads of the FastAPI engine can be scaled independently from the standard web traffic handled by Laravel.
*   **Simplified Frontend Logic:** The frontend can easily route requests based on the URL prefix without needing complex proxy rules.
*   **Improved Python Codebase:** Packaging the Python code and standardizing on `uv` will lead to better code organization, easier testing, and instant dependency resolution.
*   **Unified Auth:** A single source of truth for user authentication simplifies the security model.

### Negative
*   **Initial Refactoring Overhead:** Moving existing routes and logic to adhere to these new boundaries will require significant effort.
*   **Cross-Service Communication:** Features that require data from both domains may require cross-service API calls or reliance on the shared database/event bus, adding complexity compared to a monolith.
*   **Shared Secret Management:** The JWT secret must be securely distributed and synchronized between the two services.