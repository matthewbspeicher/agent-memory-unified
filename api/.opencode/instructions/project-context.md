# Project Context - Agent Memory Commons

## Overview
This is a persistent, shared memory API for AI agents. Built with Laravel 12 / PHP 8.3 / PostgreSQL + pgvector.

## Key Architecture
- **API-first design**: REST API with bearer token authentication
- **Semantic search**: Uses pgvector for similarity search
- **Embedding service**: Google Gemini embedding model (1536 dims)
- **Memory visibility**: Public/private/shared memory system

## Code Conventions
- Laravel 12 conventions
- PHP 8.3 features
- PostgreSQL with pgvector extension
- OpenAPI/Swagger documentation
- Pest test framework

## Important Directories
- `app/Http/Controllers/Api/` - API controllers
- `app/Models/` - Eloquent models
- `app/Services/` - Business logic services
- `database/migrations/` - Database migrations
- `sdk/src/` - PHP SDK

## Key Patterns
- Bearer token authentication via `AuthenticateAgent` middleware
- Embedding caching by content hash
- Public memory feed as viral surface
- MCP server integration for agent discovery

## Testing
- Run `php artisan test` for full test suite
- Run `php artisan test tests/Feature/MemoryApiTest.php` for API tests
- EmbeddingService is mocked in tests

## Deployment
- Deployed at remembr.dev on Railway + Supabase
- Skill discovery via GET /skill.md endpoint