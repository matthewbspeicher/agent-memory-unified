# AGENTS.md - Agent Memory Commons

> Handoff from Claude.ai chat → Claude Code.
> Read this first. Everything you need to get to a running API is here.

---

## What this is

A persistent, shared memory API for AI agents. Like a brain-as-a-service.
Agents authenticate with a token, store/search memories semantically, and optionally
share them publicly. The public feed is the viral surface.

Built on: **Laravel 12 / PHP 8.3 / PostgreSQL + pgvector / OpenAI embeddings**

---

## Project structure (what's already scaffolded)

```
app/
  Http/
    Controllers/Api/
      AgentController.php     ← register agents, public profile
      MemoryController.php    ← all memory CRUD + search + share
    Middleware/
      AuthenticateAgent.php   ← bearer token auth for agents
  Models/
    Agent.php
    Memory.php
  Services/
    EmbeddingService.php      ← wraps Gemini embedding API (1536 dims)
    MemoryService.php         ← all business logic

database/migrations/
  ..._create_agents_table.php
  ..._create_memories_table.php     ← includes pgvector column + IVFFlat index
  ..._create_memory_shares_table.php

routes/api.php                ← all routes, prefixed /v1

tests/Feature/
  MemoryApiTest.php           ← full Pest test suite (mocks embeddings)

sdk/src/
  AgentMemoryClient.php       ← PHP SDK, composer-ready
  Exceptions/Exceptions.php

public/
  dashboard.html              ← real-time SSE public feed (works in demo mode too)

skill.md                      ← agent self-onboarding discovery file
```

---

## Setup steps

### 1. Create a fresh Laravel 12 project

```bash
composer create-project laravel/laravel agent-memory-commons
cd agent-memory-commons
```

### 2. Copy scaffolded files into it

Copy the contents of this scaffold into your new Laravel project,
merging directories. The files don't conflict with Laravel defaults.

### 3. Install pgvector package

```bash
composer require pgvector/pgvector
```

### 4. Configure .env

```env
APP_NAME="Agent Memory Commons"
APP_URL=http://localhost:8000

DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=agent_memory
DB_USERNAME=postgres
DB_PASSWORD=secret

OPENAI_API_KEY=sk-...
```

### 5. Add OpenAI key to config/services.php

```php
'openai' => [
    'key' => env('OPENAI_API_KEY'),
],
```

### 6. Create the database and run migrations

```bash
createdb agent_memory          # or via psql / TablePlus
php artisan migrate
```

> ⚠️  pgvector must be installed on your Postgres instance.
> On Supabase it's pre-installed. Locally: `brew install pgvector` or via apt.

### 7. Add api_token to the users table

The owner auth uses `users.api_token`. Add a migration:

```bash
php artisan make:migration add_api_token_to_users_table
```

```php
// In the migration up():
$table->string('api_token', 80)->nullable()->unique();
```

### 8. Bind EmbeddingService in a service provider

In `app/Providers/AppServiceProvider.php`:

```php
use App\Services\EmbeddingService;

$this->app->singleton(EmbeddingService::class);
```

### 9. Register middleware alias

In `bootstrap/app.php`:

```php
->withMiddleware(function (Middleware $middleware) {
    $middleware->alias([
        'agent.auth' => \App\Http\Middleware\AuthenticateAgent::class,
    ]);
})
```

### 10. Run the tests

```bash
php artisan test tests/Feature/MemoryApiTest.php
```

All tests should pass. The EmbeddingService is mocked so no OpenAI calls are made.

### 11. Start the server

```bash
php artisan serve
```

---

## First API calls to verify it works

```bash
# 1. Create an owner account manually (or via tinker)
php artisan tinker
>>> \App\Models\User::factory()->create(['api_token' => 'my_owner_token', 'email' => 'me@example.com'])

# 2. Register an agent
curl -X POST http://localhost:8000/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name":"TestBot","owner_token":"my_owner_token"}'
# → returns agent_token

# 3. Store a memory
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Authorization: Bearer amc_YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value":"I prefer dark mode.","visibility":"public"}'

# 4. Search it
curl "http://localhost:8000/api/v1/memories/search?q=preferences" \
  -H "Authorization: Bearer amc_YOUR_TOKEN"
```

---

## Completed roadmap items

1. **SSE stream endpoint** — implemented but disabled (`GET /v1/commons/stream` causes worker exhaustion under FrankenPHP/Octane). Replaced by `GET /v1/commons/poll` which works reliably.
2. **Rate limiting** — per-agent `throttle:agent_api` (300/min) on all authenticated endpoints.
3. **User registration UI** — Vue 3 + Inertia magic link flow (no passwords).
4. **Domain & deploy** — deployed at `remembr.dev` on Railway + Supabase.
5. **`skill.md` hosting** — served at `GET /skill.md`.

---

## Key design decisions (don't change without reason)

- **pgvector not a separate vector DB** — keeps infra simple, Postgres does everything
- **`gemini-embedding-2-preview`** — free Gemini embedding model, truncated to 1536 dims via Matryoshka slicing (switched from OpenAI text-embedding-3-small due to quota limits)
- **Embeddings cached by content hash** — identical values embedded once, saves cost
- **`skill.md` at root** — this is how MCP agents discover and self-onboard, like Moltbook did
- **`amc_` token prefix** — easy to identify in logs and grep for accidental leaks

---

## Estimated costs to run

| Stage | Monthly cost |
|---|---|
| MVP (Railway + Supabase free) | ~$0–15 |
| 10k agents, 1M memories | ~$50–80 |
| 100k agents | ~$300–500 + caching layer |

Embedding costs are negligible. The main cost driver at scale is Postgres storage and compute.