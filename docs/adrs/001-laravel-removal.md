# ADR-001: Replace Laravel API with FastAPI

## Status
Accepted

## Context
The project historically used a Laravel PHP API alongside the Python FastAPI trading engine. This created:
- Two codebases to maintain
- Inconsistent API patterns
- Database confusion (Laravel tables + Python tables)
- Additional Docker service overhead

## Decision
Remove the Laravel API entirely, keeping only the FastAPI trading engine. All trading functionality runs through FastAPI at port 8080.

## Rationale
- Laravel was only handling historical vector memory (now deprecated)
- FastAPI can serve all current and future API needs
- Eliminates 46 unused database tables
- Reduces Docker Compose complexity
- Single language (Python) for all backend logic

## Consequences
- All routes consolidated in `trading/api/app.py`
- Vector memory patterns preserved in `docs/reference/laravel-api/`
- 44 trading tables recreated in PostgreSQL via `scripts/init-trading-tables.sql`

## Metadata
- Date: 2026-04-09
- Deciders: Claude, Gemini, User
- Related PRs: Cleanup session