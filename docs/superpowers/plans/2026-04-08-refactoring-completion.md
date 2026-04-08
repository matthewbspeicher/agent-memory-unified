# Refactoring Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining backend, API, and frontend refactoring tasks to finalize the Agent Memory Unified architecture cleanup.

**Architecture:** Decompose the Python LLM client into a provider registry, move FastAPI global state to dependency injection, introduce Laravel policies for authorization, split monolithic Laravel services (`MemoryService` and `TradingService`), and unify the frontend API clients to use a consistent authentication pattern.

**Tech Stack:** Python 3.14 (FastAPI), PHP 8.3 (Laravel 12), React 19 (TypeScript, Vite)

---

### Task 1: Phase 3.4 - LLMClient to Provider Registry

Extract provider-specific logic from `trading/llm/client.py` into a registry pattern.

**Files:**
- Create: `trading/llm/providers.py`
- Modify: `trading/llm/client.py`
- Create/Modify: `trading/tests/test_llm_client.py`

- [ ] **Step 1: Write the failing test for the new provider registry**

```python
# trading/tests/test_llm_client.py
import pytest
from llm.providers import ProviderRegistry, BaseProvider, LLMResult

class DummyProvider(BaseProvider):
    name = "dummy"
    async def chat(self, system: str, messages: list[dict], **kwargs) -> LLMResult | None:
        return LLMResult(text="dummy response", provider="dummy", model="dummy", latency_ms=10)

def test_provider_registry():
    registry = ProviderRegistry()
    registry.register(DummyProvider())
    assert "dummy" in registry.providers
    provider = registry.get("dummy")
    assert provider.name == "dummy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest trading/tests/test_llm_client.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'llm.providers'"

- [ ] **Step 3: Implement the provider registry and base classes**

```python
# trading/llm/providers.py
from abc import ABC, abstractmethod
from typing import Any
from .client import LLMResult, ProviderName

class BaseProvider(ABC):
    name: ProviderName

    @abstractmethod
    async def chat(self, system: str, messages: list[dict[str, str]], **kwargs) -> LLMResult | None:
        pass

class ProviderRegistry:
    def __init__(self):
        self.providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        self.providers[provider.name] = provider

    def get(self, name: str) -> BaseProvider | None:
        return self.providers.get(name)
```

- [ ] **Step 4: Refactor `LLMClient` in `client.py` to use the registry**

Modify `trading/llm/client.py` to extract `_try_anthropic_chat`, `_try_groq_chat`, etc. into subclasses of `BaseProvider` and use `ProviderRegistry` inside `LLMClient`. Move the imports to the top or inside the methods as before. 

- [ ] **Step 5: Run tests and verify they pass**

Run: `pytest trading/tests/test_llm_client.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add trading/tests/test_llm_client.py trading/llm/providers.py trading/llm/client.py
git commit -m "refactor(llm): extract providers to registry pattern"
```

### Task 2: Phase 3.5 - `memory.py` globals to services

Move `_memory_client_registry` and `_shared_memory_client` from `trading/api/routes/memory.py` into a dependency injection service.

**Files:**
- Create: `trading/api/services/memory_registry.py`
- Modify: `trading/api/routes/memory.py`
- Modify: `trading/api/dependencies.py`
- Test: `trading/tests/api/test_memory_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/api/test_memory_registry.py
import pytest
from api.services.memory_registry import MemoryRegistry

def test_memory_registry():
    registry = MemoryRegistry()
    registry.register_client("agent1", "client1")
    assert registry.get_client("agent1") == "client1"
    
    registry.register_shared("shared_client")
    assert registry.get_shared() == "shared_client"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest trading/tests/api/test_memory_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `MemoryRegistry`**

```python
# trading/api/services/memory_registry.py
from typing import Any

class MemoryRegistry:
    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._shared: Any = None

    def register_client(self, agent_name: str, client: Any) -> None:
        self._clients[agent_name] = client

    def get_client(self, agent_name: str) -> Any | None:
        return self._clients.get(agent_name)

    def register_shared(self, client: Any) -> None:
        self._shared = client

    def get_shared(self) -> Any | None:
        return self._shared

# Global instance for DI
memory_registry = MemoryRegistry()
```

- [ ] **Step 4: Add dependency to `trading/api/dependencies.py`**

```python
# In trading/api/dependencies.py
from .services.memory_registry import memory_registry, MemoryRegistry

def get_memory_registry() -> MemoryRegistry:
    return memory_registry
```

- [ ] **Step 5: Refactor `trading/api/routes/memory.py`**

Remove global variables and `register_memory_client` / `register_shared_client`. Inject `MemoryRegistry` into the route functions:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from api.dependencies import get_memory_registry
from api.services.memory_registry import MemoryRegistry

@router.get("/index")
async def get_memory_index(registry: MemoryRegistry = Depends(get_memory_registry)) -> dict:
    shared = registry.get_shared()
    if not shared:
        raise HTTPException(status_code=503, detail="Shared memory system not configured")
    # ...
```

- [ ] **Step 6: Run tests and verify they pass**

Run: `pytest trading/tests/api/test_memory_registry.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add trading/tests/api/test_memory_registry.py trading/api/services/memory_registry.py trading/api/routes/memory.py trading/api/dependencies.py
git commit -m "refactor(api): replace memory globals with dependency injection"
```

### Task 3: Phase 4.1 - Laravel Workspace/Auth to Policies

Create Laravel Policies for Memory authorization.

**Files:**
- Create: `api/app/Policies/MemoryPolicy.php`
- Modify: `api/app/Providers/AuthServiceProvider.php` (if needed, or use auto-discovery)
- Modify: `api/app/Http/Controllers/Api/MemoryController.php`
- Test: `api/tests/Feature/MemoryPolicyTest.php`

- [ ] **Step 1: Write the failing test**

```php
// api/tests/Feature/MemoryPolicyTest.php
<?php
namespace Tests\Feature;
use Tests\TestCase;
use App\Models\User;
use App\Models\Memory;
use App\Models\Workspace;

class MemoryPolicyTest extends TestCase
{
    public function test_user_can_view_own_workspace_memory()
    {
        $user = User::factory()->create();
        $workspace = Workspace::factory()->create(['user_id' => $user->id]);
        $memory = Memory::factory()->create(['workspace_id' => $workspace->id]);
        
        $this->assertTrue($user->can('view', $memory));
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && php artisan test --filter MemoryPolicyTest`
Expected: FAIL

- [ ] **Step 3: Implement `MemoryPolicy.php`**

```php
// api/app/Policies/MemoryPolicy.php
<?php
namespace App\Policies;
use App\Models\User;
use App\Models\Memory;

class MemoryPolicy
{
    public function view(User $user, Memory $memory): bool
    {
        return $user->workspaces()->where('id', $memory->workspace_id)->exists();
    }
    
    public function update(User $user, Memory $memory): bool
    {
        return $this->view($user, $memory);
    }
    
    public function delete(User $user, Memory $memory): bool
    {
        return $this->view($user, $memory);
    }
}
```

- [ ] **Step 4: Update `MemoryController.php` to use the policy**

```php
// In api/app/Http/Controllers/Api/MemoryController.php
public function show(Memory $memory)
{
    $this->authorize('view', $memory);
    return response()->json($memory);
}
```
*(Apply to `update`, `destroy` etc.)*

- [ ] **Step 5: Run tests and verify they pass**

Run: `cd api && php artisan test --filter MemoryPolicyTest`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/tests/Feature/MemoryPolicyTest.php api/app/Policies/MemoryPolicy.php api/app/Http/Controllers/Api/MemoryController.php
git commit -m "refactor(api): extract memory authorization into policies"
```

### Task 4: Phase 4.2 - Split MemoryService.php

Split the monolithic `MemoryService.php` into specific services.

**Files:**
- Create: `api/app/Services/MemoryWriter.php`
- Create: `api/app/Services/MemoryReader.php`
- Create: `api/app/Services/MemorySharing.php`
- Modify: `api/app/Services/MemoryService.php` (Facade/delegator or delete)
- Modify: Controllers using `MemoryService`

- [ ] **Step 1: Create `MemoryWriter.php`**

Extract `store`, `update`, `delete`, `compact` from `MemoryService.php` to `MemoryWriter.php`.
```php
// api/app/Services/MemoryWriter.php
<?php
namespace App\Services;
class MemoryWriter {
    public function __construct(
        private readonly \App\Contracts\EmbeddingServiceInterface $embeddings,
        private readonly \App\Contracts\SummarizationServiceInterface $summarizer,
    ) {}
    // Implement store, update, delete, compact...
}
```

- [ ] **Step 2: Create `MemoryReader.php`**

Extract `findByKey`, `listForAgent`, `recordAccess`, `recordFeedback`.

- [ ] **Step 3: Create `MemorySharing.php`**

Extract `shareWith`, `revokeShare`.

- [ ] **Step 4: Update DI bindings and Controllers**

Update `MemoryController.php` and others to inject `MemoryWriter` or `MemoryReader` instead of `MemoryService`. If `MemoryService` is heavily used, change it to delegate to these new classes for backwards compatibility during transition.

- [ ] **Step 5: Run tests to verify existing tests pass**

Run: `cd api && php artisan test --filter Memory`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/app/Services/Memory* api/app/Http/Controllers/Api/MemoryController.php
git commit -m "refactor(api): split MemoryService into writer, reader, and sharing services"
```

### Task 5: Phase 4.3 - Split TradingService.php

Split the monolithic `TradingService.php`.

**Files:**
- Create: `api/app/Services/TradeProcessor.php`
- Create: `api/app/Services/PositionManager.php`
- Modify: `api/app/Services/TradingService.php`
- Modify: `api/tests/Unit/TradingServiceTest.php`

- [ ] **Step 1: Create `TradeProcessor.php`**

Extract `computeChildPnl` and `processChildTrade` from `TradingService.php`.

```php
// api/app/Services/TradeProcessor.php
<?php
namespace App\Services;
class TradeProcessor {
    public function computeChildPnl(...) { ... }
    public function processChildTrade(...) { ... }
}
```

- [ ] **Step 2: Create `PositionManager.php`**

Extract `recalculatePosition` and `recalculateStats`.

- [ ] **Step 3: Update `TradingServiceTest.php`**

Rename and split the tests to `TradeProcessorTest.php` and `PositionManagerTest.php`.

- [ ] **Step 4: Run tests**

Run: `cd api && php artisan test --filter Trading`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/app/Services/TradeProcessor.php api/app/Services/PositionManager.php api/app/Services/TradingService.php api/tests/Unit/
git commit -m "refactor(api): split TradingService into TradeProcessor and PositionManager"
```

### Task 6: Phase 5.1 - Frontend Auth Unification

Unify how the frontend handles API configuration and authorization tokens for both Laravel (`/api/v1`) and FastAPI (`/engine/v1`).

**Files:**
- Create: `frontend/src/lib/api/factory.ts`
- Modify: `frontend/src/lib/api/client.ts`
- Modify: `frontend/src/lib/api/competition.ts`

- [ ] **Step 1: Create the centralized API factory**

```typescript
// frontend/src/lib/api/factory.ts
import axios, { AxiosInstance } from 'axios';

export function createApiClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL });

  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Also add X-API-Key if available for engine routes
    const apiKey = import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : '');
    if (apiKey && baseURL.includes('/engine')) {
        config.headers['X-API-Key'] = apiKey;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        localStorage.removeItem('auth_token');
        window.dispatchEvent(new Event('unauthorized'));
      }
      return Promise.reject(error);
    }
  );

  return client;
}
```

- [ ] **Step 2: Update existing clients to use the factory**

```typescript
// frontend/src/lib/api/client.ts
import { createApiClient } from './factory';

export const api = createApiClient('/api');
```

```typescript
// frontend/src/lib/api/competition.ts
import { createApiClient } from './factory';

const getBaseUrl = () => {
  if (import.meta.env.DEV) {
    return '/engine/v1';
  }
  return import.meta.env.VITE_TRADING_API_URL 
    ? `${import.meta.env.VITE_TRADING_API_URL}/engine/v1`
    : 'http://localhost:8080/engine/v1';
};

const tradingApi = createApiClient(getBaseUrl());
// ... remove the previous axios.create logic
```

- [ ] **Step 3: Run TypeScript checks to verify**

Run: `cd frontend && npm run tsc` (or equivalent)
Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/factory.ts frontend/src/lib/api/client.ts frontend/src/lib/api/competition.ts
git commit -m "refactor(frontend): unify api client creation and auth token injection"
```
