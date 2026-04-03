# Specification: Upgrade to Laravel 13

## Overview
This track handles the upgrade of the application's core backend framework to Laravel 13, ensuring that all existing functionality, integrations, and performance standards remain intact.

## Functional Requirements
- Upgrade the `laravel/framework` dependency to version `^13.0`.
- Upgrade all secondary dependencies (e.g., Inertia, Vue, Tailwind, PHP if required) to their **latest stable** versions.
- Apply necessary code changes required by Laravel 13's breaking changes, utilizing automated upgrade tools (e.g., "Laravel Boost" or Laravel Shift) where possible to streamline the transition.

## Non-Functional Requirements
- **Performance:** The application must remain compatible with Laravel Octane and FrankenPHP for high-performance request handling.
- **Stability:** The hybrid search infrastructure (pgvector cosine similarity + PostgreSQL GIN full-text search) and integrations with Gemini embeddings must remain completely stable.

## Acceptance Criteria
- `composer update` succeeds without conflicts.
- The application boots successfully on Laravel 13.
- The automated test suite passes with >80% coverage.
- Comprehensive manual and automated regression testing succeeds across all core areas:
  - Auth & Permissions
  - API & Semantic Search
  - Agent Workspaces
  - Performance (Octane & FrankenPHP)

## Out of Scope
- Architectural overhauls or new feature additions unrelated to the upgrade.
- Upgrades to external services or databases unless strictly required by Laravel 13.