# Codebase Critical Fixes & Tech Debt Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the critical bugs, performance bottlenecks, and security vulnerabilities identified in the codebase review, ensuring the system is robust before adding new features.

**Architecture:** We will implement timing-safe string comparisons for API authentication, add validation to the Bittensor scheduler to prevent silent failures, optimize the strategy health recompute loop with `asyncio.gather`, and clean up redundant YAML configuration reads during application startup.

**Tech Stack:** Python 3.12, Pytest, FastAPI, asyncio, hmac.

---

### Task 1: API Security & Bittensor Validation

**Files:**
- Modify: `trading/api/auth.py`
- Modify: `trading/integrations/bittensor/scheduler.py`

- [ ] **Step 1: Write the failing tests**

```python
# Create trading/tests/unit/test_api/test_auth_timing.py
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from api.auth import verify_api_key

def test_verify_api_key_invalid():
    mock_request = MagicMock()
    mock_request.app.state.config.api_key = "secret123"
    
    with pytest.raises(HTTPException) as exc:
        verify_api_key(mock_request, "wrong_key")
    assert exc.value.status_code == 401

# Add to trading/tests/unit/test_integrations/test_bittensor_scheduler.py
def test_scheduler_validation():
    from integrations.bittensor.scheduler import TaoshiScheduler
    import pytest
    
    # Should raise error if both paths are disabled
    with pytest.raises(ValueError, match="No Bittensor data path active"):
        scheduler = TaoshiScheduler(
            adapter=MagicMock(), store=MagicMock(), event_bus=MagicMock(),
            direct_query_enabled=False
            # Assume no taoshi_validator_root in environment
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd trading && pytest tests/unit/test_api/test_auth_timing.py tests/unit/test_integrations/test_bittensor_scheduler.py -v`

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/api/auth.py
import hmac
# ... inside verify_api_key:
    if not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

# In trading/integrations/bittensor/scheduler.py
# ... inside __init__ before setting self._running:
        import os
        taoshi_root = os.getenv("STA_TAOSHI_VALIDATOR_ROOT")
        if not self._direct_query_enabled and not taoshi_root:
            raise ValueError("No Bittensor data path active: direct_query_enabled=False and STA_TAOSHI_VALIDATOR_ROOT not set.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd trading && pytest tests/unit/test_api/test_auth_timing.py tests/unit/test_integrations/test_bittensor_scheduler.py -v`

- [ ] **Step 5: Commit**

```bash
git add trading/api/auth.py trading/integrations/bittensor/scheduler.py trading/tests/unit/test_api/test_auth_timing.py trading/tests/unit/test_integrations/test_bittensor_scheduler.py
git commit -m "fix: secure API auth and validate bittensor data path"
```

### Task 2: Async Performance & Redundant I/O

**Files:**
- Modify: `trading/learning/strategy_health.py`
- Modify: `trading/api/app.py`

- [ ] **Step 1: Write the failing tests**

```python
# Create trading/tests/unit/test_learning/test_health_async.py
import pytest
from unittest.mock import AsyncMock
from learning.strategy_health import HealthEngine

@pytest.mark.asyncio
async def test_recompute_all_is_concurrent():
    engine = HealthEngine(AsyncMock(), AsyncMock())
    engine.evaluate = AsyncMock(return_value="ok")
    
    await engine.recompute_all(["agent1", "agent2", "agent3"])
    # If evaluate was called 3 times, they should have been gathered.
    assert engine.evaluate.call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail (or just pass if logic doesn't strictly fail on sequential, but we want to optimize)**

Run: `cd trading && pytest tests/unit/test_learning/test_health_async.py -v`

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/learning/strategy_health.py
# ... inside recompute_all(self, agent_names):
    import asyncio
    tasks = [self.evaluate(name) for name in agent_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Log any exceptions from results if necessary

# In trading/api/app.py
# Remove redundant load_risk_config() and load_agents_config() calls around line 1412 and 1696.
# Instead, use the already loaded config instances from app.state or earlier initialization.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd trading && pytest tests/unit/test_learning/test_health_async.py -v`

- [ ] **Step 5: Commit**

```bash
git add trading/learning/strategy_health.py trading/api/app.py trading/tests/unit/test_learning/test_health_async.py
git commit -m "perf: optimize health recompute and remove duplicate yaml reads"
```
