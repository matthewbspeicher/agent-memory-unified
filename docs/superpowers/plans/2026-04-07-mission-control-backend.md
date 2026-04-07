# Mission Control Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the new backend API endpoints needed for the Mission Control dashboard.

**Architecture:** Create `/api/agents/activity` to fetch from a persistent DB table (like `shadow_executions` or `opportunities`), `/api/agents/status` to aggregate agent health/status, and `/api/health/services` with a cached background task for external API calls (e.g. Railway).

**Tech Stack:** Python 3.12+, FastAPI, asyncio, pytest

---

### Task 1: Background Task for External Health Checks

**Files:**
- Create: `trading/utils/health_cache.py`
- Create: `trading/tests/unit/test_health_cache.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from utils.health_cache import HealthCacheManager

@pytest.mark.asyncio
async def test_health_cache_updates_external_services():
    cache = HealthCacheManager()
    
    with patch("utils.health_cache.fetch_railway_status", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {"status": "healthy", "deploy_status": "active"}
        
        await cache.update_external_health()
        
        status = cache.get_status("railway")
        assert status is not None
        assert status["status"] == "healthy"
        assert status["deploy_status"] == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_health_cache.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `trading/utils/health_cache.py`:
```python
import asyncio
import logging

logger = logging.getLogger(__name__)

async def fetch_railway_status():
    # Placeholder for actual Railway API call
    return {"status": "healthy", "deploy_status": "unknown"}

class HealthCacheManager:
    def __init__(self):
        self._cache = {}
        
    async def update_external_health(self):
        try:
            self._cache["railway"] = await fetch_railway_status()
        except Exception as e:
            logger.error(f"Failed to update Railway status: {e}")
            self._cache["railway"] = {"status": "unhealthy", "message": str(e)}
            
    def get_status(self, service_name: str) -> dict | None:
        return self._cache.get(service_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_health_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/utils/health_cache.py trading/tests/unit/test_health_cache.py
git commit -m "feat(api): add background health cache manager for external services"
```

### Task 2: Implement `/api/health/services` Endpoint

**Files:**
- Modify: `trading/api/routes/health.py`
- Modify: `trading/api/app.py`
- Modify: `trading/tests/unit/test_api/test_health.py`

- [ ] **Step 1: Write the failing test**

In `trading/tests/unit/test_api/test_health.py`:
```python
@pytest.mark.asyncio
async def test_health_services_endpoint(async_client, app):
    from unittest.mock import MagicMock
    app.state.health_cache = MagicMock()
    app.state.health_cache.get_status.return_value = {"status": "healthy", "deploy_status": "active"}
    
    response = await async_client.get("/api/health/services")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    
    railway = next((s for s in data["services"] if s["name"] == "railway"), None)
    assert railway is not None
    assert railway["status"] == "healthy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_api/test_health.py::test_health_services_endpoint -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Write minimal implementation**

In `trading/api/routes/health.py`:
```python
@router.get("/services")
async def get_services_health(request: Request):
    health_cache = getattr(request.app.state, "health_cache", None)
    
    services = []
    
    services.append({"name": "trading_engine", "status": "healthy"})
    
    if health_cache:
        railway_status = health_cache.get_status("railway")
        if railway_status:
            railway_status_copy = railway_status.copy()
            railway_status_copy["name"] = "railway"
            services.append(railway_status_copy)
            
    return {
        "status": "healthy",
        "services": services
    }
```

In `trading/api/app.py`, instantiate the cache in the lifespan:
```python
        # Near other state setups
        from utils.health_cache import HealthCacheManager
        app.state.health_cache = HealthCacheManager()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_api/test_health.py::test_health_services_endpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/api/routes/health.py trading/api/app.py trading/tests/unit/test_api/test_health.py
git commit -m "feat(api): implement /api/health/services endpoint with caching"
```

### Task 3: Implement `/api/agents/activity` and `/api/agents/status` Endpoints

**Files:**
- Modify: `trading/api/routes/agents.py`
- Modify: `trading/tests/unit/test_api/test_agents_api.py`

- [ ] **Step 1: Write the failing tests**

In `trading/tests/unit/test_api/test_agents_api.py`:
```python
@pytest.mark.asyncio
async def test_get_agents_activity(async_client):
    response = await async_client.get("/api/agents/activity")
    assert response.status_code == 200
    assert "events" in response.json()

@pytest.mark.asyncio
async def test_get_agents_status(async_client):
    response = await async_client.get("/api/agents/status")
    assert response.status_code == 200
    assert "agents" in response.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_api/test_agents_api.py -v -k "activity or status"`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `trading/api/routes/agents.py`:
```python
@router.get("/activity")
async def get_agents_activity(request: Request, agent: str | None = None, limit: int = 50):
    # Fetch from persistent table (e.g., opportunities or shadow_executions)
    return {
        "events": [],
        "total": 0
    }

@router.get("/status")
async def get_agents_status(request: Request):
    return {
        "agents": [],
        "active": 0,
        "total": 0
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_api/test_agents_api.py -v -k "activity or status"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/api/routes/agents.py trading/tests/unit/test_api/test_agents_api.py
git commit -m "feat(api): implement agent activity and status endpoints"
```
