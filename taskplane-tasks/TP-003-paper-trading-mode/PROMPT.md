# Task: TP-003 - Paper Trading Mode

**Created:** 2026-04-07
**Size:** L

## Review Level: 2 (Plan and Code)

**Assessment:** New execution path with simulated order fills. Touches broker abstraction and position tracking.
**Score:** 4/8 — Blast radius: 1, Pattern novelty: 1, Security: 1, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-003-paper-trading-mode/
```

## Mission

Implement a paper trading mode that validates the full signal→trade pipeline without real money. Create a `PaperBroker` that implements the same interface as the IBKR broker but simulates order fills using current market prices. Track simulated positions, P&L, and trade history in the database.

## Dependencies

- **Task:** TP-002 (signal pipeline must work end-to-end)

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `CLAUDE.md` — architecture overview
- `trading/broker/` — existing broker interface and IBKR implementation

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading, postgres)

## File Scope

- `trading/broker/paper.py` (new)
- `trading/broker/models.py` (may need interface additions)
- `trading/api/app.py` (broker selection logic)
- `trading/config.py` (paper mode config)
- `trading/tests/unit/test_paper_broker.py` (new)
- `trading/tests/live_paper/*`

## Steps

### Step 0: Preflight
- [ ] Read existing broker interface in `trading/broker/`
- [ ] Read `trading/tests/live_paper/` for existing paper trading test patterns
- [ ] Read config.py for broker initialization

### Step 1: Implement PaperBroker
- [ ] Create `trading/broker/paper.py` implementing the broker interface
- [ ] Simulate market orders with instant fill at current price (from DataBus)
- [ ] Track positions in-memory with optional DB persistence
- [ ] Calculate unrealized P&L using latest prices
- [ ] Support position close/flatten operations
- [ ] Add `STA_PAPER_TRADING=true` config flag to `config.py`

### Step 2: Wire Into App
- [ ] In `api/app.py`, select PaperBroker when `STA_PAPER_TRADING=true`
- [ ] Add paper trading status to dashboard API endpoints
- [ ] Log all paper trades clearly with `[PAPER]` prefix

### Step 3: Write Tests
- [ ] Create `trading/tests/unit/test_paper_broker.py`
- [ ] Test order fill simulation, position tracking, P&L calculation

### Step 4: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 5: Documentation & Delivery
- [ ] Document paper trading mode in README or CLAUDE.md
- [ ] Discoveries logged

## Documentation Requirements
**Must Update:** `CLAUDE.md` — add paper trading section
**Check If Affected:** `taskplane-tasks/CONTEXT.md`

## Completion Criteria
- [ ] PaperBroker passes all broker interface tests
- [ ] Paper trades logged and P&L tracked
- [ ] Config flag switches between paper and live

## Git Commit Convention
- `feat(TP-003): complete Step N — description`

## Do NOT
- Enable real trading by default
- Modify the IBKR broker code
- Skip the config flag (must be explicit opt-in)

---

## Amendments (Added During Execution)
