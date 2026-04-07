# Task: TP-004 - Trading Activity Dashboard

**Created:** 2026-04-07
**Size:** M

## Review Level: 1 (Plan Only)

**Assessment:** Frontend-only changes extending existing dashboard. Low risk.
**Score:** 2/8 — Blast radius: 1, Pattern novelty: 1, Security: 0, Reversibility: 0

## Canonical Task Folder

```
taskplane-tasks/TP-004-trading-activity-dashboard/
```

## Mission

Extend the existing Bittensor dashboard at `/bittensor` with panels for: signal flow rate (signals/minute from bridge), strategy decisions (consensus signals generated), active positions, and P&L tracking. Add a new `/trading` page for the full trading view.

## Dependencies

- **Task:** TP-002 (needs working signal pipeline for meaningful data)

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `frontend/src/pages/BittensorNode.tsx` — existing dashboard
- `frontend/src/lib/api/bittensor.ts` — API client

## Environment

- **Workspace:** `frontend/`
- **Services required:** Docker (frontend, trading)

## File Scope

- `frontend/src/pages/TradingDashboard.tsx` (new)
- `frontend/src/pages/BittensorNode.tsx` (enhanced)
- `frontend/src/lib/api/trading.ts` (new)
- `frontend/src/components/SignalFlowChart.tsx` (new)
- `frontend/src/components/PositionsTable.tsx` (new)
- `trading/api/routes/bittensor.py` (add signal metrics endpoint)

## Steps

### Step 0: Preflight
- [ ] Read existing BittensorNode.tsx and API client
- [ ] Read trading API routes for available data
- [ ] Check what metrics are already exposed

### Step 1: Add API Endpoints for Trading Metrics
- [ ] Add `/api/bittensor/signal-metrics` endpoint returning signal rates, consensus counts
- [ ] Add `/api/bittensor/positions` endpoint returning current open positions with P&L
- [ ] Add `/api/bittensor/trade-history` endpoint for recent trades

### Step 2: Build Dashboard Components
- [ ] Create `SignalFlowChart.tsx` — real-time signal rate visualization
- [ ] Create `PositionsTable.tsx` — open positions with unrealized P&L
- [ ] Create `TradingDashboard.tsx` page combining all components
- [ ] Add route to app router

### Step 3: Enhance Existing Bittensor Page
- [ ] Add signal flow summary card to BittensorNode.tsx
- [ ] Add link to full trading dashboard

### Step 4: Testing & Verification
- [ ] Frontend builds without errors: `cd frontend && npm run build`
- [ ] Components render with mock data
- [ ] Auto-refresh works (30s interval)

### Step 5: Documentation & Delivery
- [ ] Update CLAUDE.md Key URLs table
- [ ] Discoveries logged

## Documentation Requirements
**Must Update:** `CLAUDE.md` — add trading dashboard URL
**Check If Affected:** `frontend/src/components/Sidebar.tsx` — add nav link

## Completion Criteria
- [ ] New `/trading` page renders with live data
- [ ] Signal flow, positions, and P&L visible
- [ ] Auto-refresh working

## Git Commit Convention
- `feat(TP-004): complete Step N — description`

## Do NOT
- Rewrite existing BittensorNode page from scratch
- Add new npm dependencies without justification
- Hardcode API URLs (use existing api client pattern)

---

## Amendments (Added During Execution)
