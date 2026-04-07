# Task: TP-010 - Comprehensive Health Check Endpoints

**Created:** 2026-04-07
**Size:** S

## Review Level: 0 (None)

**Assessment:** Extending existing health endpoints with dependency checks. Low risk, single service.
**Score:** 1/8 — Blast radius: 0, Pattern novelty: 0, Security: 0, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-010-health-check-endpoints/
```

## Mission

Enhance the existing health endpoints (`/health`, `/health-internal`, `/health/connectivity`) to include comprehensive dependency checks for all services: PostgreSQL, Redis, Bittensor bridge status, SignalBus activity. Add a `/ready` endpoint for container orchestration (Kubernetes-style readiness probe).

## Dependencies

- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:** `trading/api/routes/health.py` — existing health endpoints

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading, postgres, redis)

## File Scope

- `trading/api/routes/health.py` (modified)
- `trading/tests/unit/test_api/test_health.py` (new or modified)

## Steps

### Step 0: Preflight
- [ ] Read existing health.py endpoints
- [ ] Identify what dependency checks already exist vs missing

### Step 1: Enhance Health Endpoints
- [ ] Add PostgreSQL connection check (query `SELECT 1`)
- [ ] Add Redis ping check
- [ ] Add TaoshiBridge status (running, last_scan_at staleness)
- [ ] Add SignalBus stats (subscriber count, last signal time)
- [ ] Add `/ready` endpoint: returns 200 only when all dependencies healthy
- [ ] Return structured JSON with per-dependency status

### Step 2: Write Tests
- [ ] Test each dependency check in isolation (mock DB/Redis)
- [ ] Test `/ready` returns 503 when a dependency is down

### Step 3: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 4: Documentation & Delivery
- [ ] Update CLAUDE.md Key URLs table
- [ ] Discoveries logged

## Completion Criteria
- [ ] `/health` returns per-dependency status
- [ ] `/ready` returns 503 when unhealthy
- [ ] All existing health tests still pass

## Git Commit Convention
- `feat(TP-010): complete Step N — description`

## Do NOT
- Remove existing health endpoint functionality
- Add authentication to health endpoints (they must be public for probes)

---

## Amendments (Added During Execution)
