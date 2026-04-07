# Technology Stack

## Core Architecture
- **Polyglot Monorepo:** A unified repository containing the API (PHP), Trading Engine (Python), and Frontend (TypeScript/React).
- **Shared Types:** Cross-service type consistency achieved via JSON Schemas and auto-generation.

## Languages & Frameworks
- **Backend (Memory API):**
  - **Language:** PHP 8.3+
  - **Framework:** Laravel 12
  - **Key Libraries:** pgvector-php, Laravel Reverb (optional), Redis client.
- **Backend (Trading Engine):**
  - **Language:** Python 3.14
  - **Framework:** FastAPI
  - **Key Libraries:** asyncpg, pydantic, redis-py.
- **Frontend (Dashboard):**
  - **Language:** TypeScript
  - **Framework:** React 19
  - **Build Tool:** Vite
  - **Key Libraries:** TanStack Query, React Router v7, Three.js (3D Knowledge Graph).

## Data & Communication
- **Primary Database:** PostgreSQL 16
  - **Extensions:** pgvector (for vector similarity search).
  - **Model:** Shared database schema accessed by both API and Trading services.
- **Event Bus:** Redis Streams
  - **Purpose:** High-throughput, low-latency event-driven communication (Laravel -> Redis -> Python).
- **Cache:** Redis

## Infrastructure & DevOps
- **Containerization:** Docker & Docker Compose
- **Reverse Proxy:** Nginx (serving as a unified gateway for all services).
- **Version Control:** Git with pre-commit hooks for type generation and linting.
- **Deployment:** Multi-container staging and production workflows.

## Testing
- **Backend:** PHPUnit (Laravel), pytest (Python).
- **Frontend:** Playwright (E2E), Vitest (Unit).
