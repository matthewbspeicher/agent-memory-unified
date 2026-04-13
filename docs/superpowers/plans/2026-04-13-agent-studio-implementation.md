# Agent Studio (Forge & Lab) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified UI to create (Forge), validate (Lab), and deploy autonomous trading/arena agents using a draft-to-live workflow.

**Architecture:** A new `identity.agent_drafts` PostgreSQL table backs the draft system. The React 19 frontend provides the builder UI with backtest result visualizations. Drafts can be promoted to live agents in the existing `agents.yaml` roster.

**Tech Stack:** Python 3.13, asyncpg, FastAPI, React 19.

**Known Limitation:** The initial backtest implementation uses synthetic metrics for UI validation. Real backtest integration with the `BacktestEngine` is tracked as a follow-up (see Task 2 notes).

---

## Task 1: Draft Data Model & Migration

**Files:**
- Create: `scripts/migrations/add-agent-drafts.sql`
- Modify: `trading/api/identity/store.py`
- Test: `trading/tests/unit/test_identity_drafts.py`

### Steps

- [ ] **Step 1: Write the SQL Migration**

```sql
-- scripts/migrations/add-agent-drafts.sql
CREATE TABLE IF NOT EXISTS identity.agent_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    system_prompt   TEXT NOT NULL,
    model           TEXT NOT NULL DEFAULT 'gpt-4o',
    hyperparameters JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'draft',
    backtest_results JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for listing drafts by status
CREATE INDEX idx_agent_drafts_status ON identity.agent_drafts(status);
```

- [ ] **Step 2: Write failing store test**

Test cases to implement:
- `test_create_and_get_draft` - Create draft, retrieve by ID, verify fields
- `test_update_draft_status` - Change status from draft → tested → deployed
- `test_update_draft_results` - Store backtest results JSON
- `test_list_drafts` - List drafts filtered by status
- `test_delete_draft` - Remove a draft

```python
# trading/tests/unit/test_identity_drafts.py
import pytest
from api.identity.store import IdentityStore

@pytest.mark.asyncio
async def test_create_and_get_draft(test_db):
    store = IdentityStore(test_db)
    draft_id = await store.create_draft(
        name="TestDraft",
        system_prompt="You are a test agent.",
        model="gpt-4o",
        hyperparameters={"temperature": 0.5}
    )
    assert draft_id is not None
    
    draft = await store.get_draft(draft_id)
    assert draft["name"] == "TestDraft"
    assert draft["status"] == "draft"
    assert draft["model"] == "gpt-4o"
    assert draft["hyperparameters"]["temperature"] == 0.5

@pytest.mark.asyncio
async def test_update_draft_results(test_db):
    store = IdentityStore(test_db)
    draft_id = await store.create_draft(name="Test", system_prompt="Test", model="gpt-4o")
    
    results = {"sharpe_ratio": 1.5, "win_rate": 0.62, "equity_curve": [...]}
    await store.update_draft_results(draft_id, results)
    
    draft = await store.get_draft(draft_id)
    assert draft["backtest_results"]["sharpe_ratio"] == 1.5
    assert draft["status"] == "tested"
```

- [ ] **Step 3: Implement store methods**

Add these methods to `IdentityStore`:
- `create_draft(name, system_prompt, model, hyperparameters) -> str`
- `get_draft(draft_id) -> dict | None`
- `update_draft_results(draft_id, results) -> None` - Sets backtest_results JSONB and status to "tested"
- `update_draft_status(draft_id, status) -> None`
- `list_drafts(status: str | None = None) -> list[dict]`
- `delete_draft(draft_id) -> bool`

Implementation notes:
- Use `json.dumps()` for JSONB parameters
- Parse JSONB returns with `json.loads()` when returning to caller
- Set `updated_at` on every mutation

- [ ] **Step 4: Run tests and verify pass**

```bash
cd trading && python -m pytest tests/unit/test_identity_drafts.py -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add scripts/migrations/add-agent-drafts.sql trading/api/identity/store.py trading/tests/unit/test_identity_drafts.py
git commit -m "feat: add agent_drafts schema and store methods"
```

---

## Task 2: Draft API Routes

**Files:**
- Modify: `trading/api/routes/agents.py` (or create new `trading/api/routes/drafts.py`)
- Test: `trading/tests/unit/test_draft_routes.py`

### Notes on Backtest Engine

The plan originally proposed a synchronous wrapper around `BacktestEngine`. However:
1. The existing `BacktestEngine` in `scripts/backtest_system.py` is designed for CLI use, not import
2. Running real backtests synchronously would block the event loop
3. The `sys.path.append` hack is fragile

**Approach for v1:** Return synthetic metrics with clear `"status": "scaffold"` marker. The frontend should display a "Real backtest pending" indicator. This unblocks UI development without pretending to have real data.

**Follow-up:** Wire to real backtest via a background task (Celery/ARQ) or synchronous subprocess call. Track separately.

### Steps

- [ ] **Step 1: Write failing route tests**

```python
# trading/tests/unit/test_draft_routes.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_draft_requires_auth(client: AsyncClient):
    """POST /api/v1/drafts without auth should return 401"""
    res = await client.post("/api/v1/drafts", json={"name": "Test", "system_prompt": "Test"})
    assert res.status_code in (401, 403)

@pytest.mark.asyncio
async def test_create_draft_with_auth(client: AsyncClient, auth_headers):
    res = await client.post(
        "/api/v1/drafts",
        json={"name": "TestAgent", "system_prompt": "You are a trader.", "model": "gpt-4o"},
        headers=auth_headers
    )
    assert res.status_code == 200
    assert "id" in res.json()["data"]

@pytest.mark.asyncio
async def test_backtest_returns_results(client: AsyncClient, auth_headers):
    # Create draft first
    create_res = await client.post("/api/v1/drafts", json={...}, headers=auth_headers)
    draft_id = create_res.json()["data"]["id"]
    
    # Run backtest
    res = await client.post(f"/api/v1/drafts/{draft_id}/backtest", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "sharpe_ratio" in data
    assert "equity_curve" in data
    assert "status" in data
```

- [ ] **Step 2: Implement API routes**

Routes to implement (in `agents.py` or new `drafts.py`):

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/drafts` | `write:orders` | Create new draft |
| GET | `/api/v1/drafts` | `write:orders` | List drafts (optional `?status=` filter) |
| GET | `/api/v1/drafts/{id}` | `write:orders` | Get draft by ID |
| POST | `/api/v1/drafts/{id}/backtest` | `write:orders` | Run backtest, store results |
| POST | `/api/v1/drafts/{id}/deploy` | `control:agents` | Promote draft to live agent |
| DELETE | `/api/v1/drafts/{id}` | `control:agents` | Delete draft |

Authentication: Use `require_scope(...)` dependency (existing pattern). All draft routes need `write:orders` at minimum. Deploy/delete need `control:agents`.

Request/Response models:
```python
class DraftCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    system_prompt: str = Field(min_length=1)
    model: str = "gpt-4o"
    hyperparameters: dict = {}

class DraftResponse(BaseModel):
    id: str
    name: str
    system_prompt: str
    model: str
    hyperparameters: dict
    status: str
    backtest_results: dict | None
    created_at: str
    updated_at: str
```

Backtest endpoint behavior:
1. Get draft from store
2. Generate synthetic metrics (status="scaffold")
3. Call `store.update_draft_results(draft_id, results)`
4. Return results

Deploy endpoint behavior (stub for v1):
1. Validate draft status is "tested"
2. Return `{"status": "deployed", "message": "Draft promoted (implementation pending)"}`
3. Full deployment to agents.yaml tracked as follow-up

- [ ] **Step 3: Run tests and commit**

```bash
cd trading && python -m pytest tests/unit/test_draft_routes.py -v --tb=short
git add trading/api/routes/agents.py trading/tests/unit/test_draft_routes.py
git commit -m "feat: add draft CRUD and backtest API routes with auth"
```

---

## Task 3: Forge UI (Creation)

**Files:**
- Create: `frontend/src/pages/Forge.tsx`
- Create: `frontend/src/pages/Forge.css` (optional, or use Tailwind)
- Modify: `frontend/src/router.tsx`

### Steps

- [ ] **Step 1: Create Forge Component**

Component requirements:
- Form with fields: Agent Name (text), System Prompt (textarea), Model (select: gpt-4o, gpt-4.1, claude-sonnet)
- Hyperparameters section: Temperature (slider 0-2), Top-P (slider 0-1) - collapsible
- "Save Draft" button - disabled until name + prompt filled
- On success: Navigate to `/studio/lab/{id}`
- Use existing `GlassCard` component with `variant="cyan"`
- Loading state during save
- Error toast on failure

API call:
```typescript
POST /api/v1/drafts
Body: { name, system_prompt, model, hyperparameters }
Headers: Include X-API-Key from existing auth context
```

- [ ] **Step 2: Add route to `router.tsx`**

Follow existing lazy-loading pattern:
```typescript
const Forge = lazy(() => import('./pages/Forge'));
// In children array:
{ path: 'studio/forge', element: <LazyPage><Forge /></LazyPage> },
```

- [ ] **Step 3: Add nav link**

Add link to Forge in the main navigation (or sidebar). Suggested label: "Agent Forge" with ⚒️ icon.

- [ ] **Step 4: Test manually and commit**

```bash
# Run frontend dev server
cd frontend && npx vite --host 0.0.0.0 --port 3000

# Verify: Navigate to /studio/forge, create draft, redirect to lab
git add frontend/src/pages/Forge.tsx frontend/src/router.tsx
git commit -m "feat(ui): add Forge page for agent draft creation"
```

---

## Task 4: Lab UI (Evaluation & Deployment)

**Files:**
- Create: `frontend/src/pages/Lab.tsx`
- Modify: `frontend/src/router.tsx`

### Steps

- [ ] **Step 1: Create Lab Component**

Component requirements:
- Receive draft ID from URL params (`/studio/lab/:id`)
- Fetch draft details on mount: `GET /api/v1/drafts/{id}`
- Display draft configuration (name, model, hyperparameters) in read-only view
- "Run Backtest" button → `POST /api/v1/drafts/{id}/backtest`
- Results display:
  - Sharpe Ratio, Win Rate, Max Drawdown as stat cards
  - Equity curve as simple line chart (use inline SVG or recharts if already installed)
  - Status indicator: show "Scaffold" badge if results.status === "scaffold"
- "Deploy Agent" button - enabled only if sharpe_ratio > 1.0 and status !== "scaffold"
  - On click: `POST /api/v1/drafts/{id}/deploy`
  - Show success toast, navigate to agents dashboard
- Loading states for backtest and deploy operations
- Error handling with toast notifications

Styling:
- Use `GlassCard` with `variant="violet"` for config panel
- Use `GlassCard` with `variant="green"` for results panel
- Follow existing typography (uppercase headers, mono font for metrics)

- [ ] **Step 2: Add route to `router.tsx`**

```typescript
const Lab = lazy(() => import('./pages/Lab'));
// In children array:
{ path: 'studio/lab/:id', element: <LazyPage><Lab /></LazyPage> },
```

- [ ] **Step 3: Test and commit**

```bash
# Verify flow: Forge → Lab → Backtest → Deploy button appears
git add frontend/src/pages/Lab.tsx frontend/src/router.tsx
git commit -m "feat(ui): add Lab page for agent evaluation and deployment"
```

---

## Task 5: Integration & Cleanup

**Files:**
- Modify: Various (as needed)
- Create: `docs/adr/XXXX-agent-studio.md` (ADR for this feature)

### Steps

- [ ] **Step 1: Write ADR**

Document the decision to use synthetic backtest metrics in v1, with rationale and follow-up plan.

- [ ] **Step 2: Update CLAUDE.md**

Add Agent Studio to the Architecture section if significant.

- [ ] **Step 3: Run full test suite**

```bash
cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30
```

- [ ] **Step 4: Final commit**

```bash
git add docs/adr/
git commit -m "docs: add ADR for Agent Studio synthetic backtest approach"
```

---

## Follow-up Items (Not in Scope)

These are tracked separately, not blocking this implementation:

1. **Real Backtest Integration** - Wire to actual `BacktestEngine` via background task
2. **Agent Deployment** - Write draft config to `agents.yaml`, restart agent framework
3. **Draft Listing Page** - Browse/manage existing drafts at `/studio`
4. **Equity Curve Visualization** - Add Recharts if not already installed, or use lightweight SVG chart
5. **Draft Duplication** - "Clone Draft" functionality
6. **Model Selection Expansion** - Add more LLM options with capability descriptions

---

## Verification Checklist

Before marking complete:

- [ ] All unit tests pass: `pytest tests/unit/ -v --tb=short --timeout=30`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] Manual flow works: Create draft → View in Lab → Run backtest → See results
- [ ] Auth enforced: Unauthenticated requests return 401
- [ ] ADR written documenting synthetic backtest decision
