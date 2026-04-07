# Task: TP-009 - Backtest Framework

**Created:** 2026-04-07
**Size:** L

## Review Level: 2 (Plan and Code)

**Assessment:** New subsystem for historical replay. Significant new code but isolated from live systems.
**Score:** 4/8 — Blast radius: 1, Pattern novelty: 2, Security: 0, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-009-backtest-framework/
```

## Mission

Build a backtesting framework that can replay historical miner positions from Taoshi's `closed/` position directories against strategies to validate performance before live deployment. The closed position files contain complete trade histories with entry/exit timestamps and prices.

## Dependencies

- **None**
- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `CLAUDE.md` — architecture
- `trading/tests/test_backtest/` — existing backtest test patterns

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading)

## File Scope

- `trading/backtest/` (new directory)
- `trading/backtest/engine.py` (new)
- `trading/backtest/data_loader.py` (new)
- `trading/backtest/report.py` (new)
- `trading/api/routes/backtest.py` (new — trigger backtest via API)
- `trading/tests/unit/test_backtest/` (new)

## Steps

### Step 0: Preflight
- [ ] Examine closed position file format in `taoshi-vanta/validation/miners/`
- [ ] Read existing backtest test patterns
- [ ] Read PaperBroker interface (from TP-003)

### Step 1: Build Data Loader
- [ ] Create `trading/backtest/data_loader.py`
- [ ] Load closed position files from Taoshi validator directories
- [ ] Parse into timeline of events (position open, order added, position closed)
- [ ] Sort chronologically across all miners

### Step 2: Build Backtest Engine
- [ ] Create `trading/backtest/engine.py`
- [ ] Replay events through SignalBus → ConsensusAggregator → Strategy pipeline
- [ ] Use PaperBroker for simulated execution
- [ ] Track: trades executed, P&L per trade, win rate, Sharpe ratio, max drawdown

### Step 3: Build Report Generator
- [ ] Create `trading/backtest/report.py`
- [ ] Generate summary: total return, win rate, Sharpe, max drawdown, per-strategy breakdown
- [ ] Output as JSON for API and human-readable text

### Step 4: Add API Endpoint
- [ ] Create `trading/api/routes/backtest.py`
- [ ] `POST /api/backtest/run` — trigger backtest with date range and strategy config
- [ ] `GET /api/backtest/results/{id}` — fetch results

### Step 5: Write Tests
- [ ] Test data loader with sample position files
- [ ] Test engine with known outcomes
- [ ] Test report calculations

### Step 6: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 7: Documentation & Delivery
- [ ] Document backtest usage
- [ ] Discoveries logged

## Completion Criteria
- [ ] Backtest runs against historical closed positions
- [ ] P&L and key metrics reported
- [ ] API endpoint functional

## Git Commit Convention
- `feat(TP-009): complete Step N — description`

## Do NOT
- Modify closed position files on disk
- Run backtests automatically on startup
- Add heavy data science dependencies (numpy ok, pandas ok, avoid sklearn)

---

## Amendments (Added During Execution)
