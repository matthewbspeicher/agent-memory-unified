# Task: TP-008 - Activate Ensemble Strategy

**Created:** 2026-04-07
**Size:** M

## Review Level: 2 (Plan and Code)

**Assessment:** Wiring existing strategy code with multi-strategy consensus. Affects trade decisions.
**Score:** 4/8 — Blast radius: 1, Pattern novelty: 1, Security: 1, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-008-ensemble-strategy-activation/
```

## Mission

Activate the existing ensemble/multi-factor strategy code so Bittensor miner signals are ONE input alongside technical indicators (RSI, momentum, volume). The files `ensemble_optimizer.py`, `multi_factor.py`, `multi_timeframe_consensus.py` exist but may not be wired into the agent runner. Audit, fix, and activate them as part of a multi-strategy consensus approach.

## Dependencies

- **None**
- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `trading/strategies/ensemble_optimizer.py`
- `trading/strategies/multi_factor.py`
- `trading/agents/runner.py` — how agents are registered and run

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading)

## File Scope

- `trading/strategies/ensemble_optimizer.py` (audit/fix)
- `trading/strategies/multi_factor.py` (audit/fix)
- `trading/strategies/multi_timeframe_consensus.py` (audit/fix)
- `trading/agents/config.py` (register strategies)
- `trading/api/app.py` (wire strategies)
- `trading/tests/unit/test_ensemble.py` (new)

## Steps

### Step 0: Preflight
- [ ] Audit all strategy files in `trading/strategies/` — which are functional vs stubs
- [ ] Read agent runner and config to understand registration
- [ ] Identify which strategies have working `scan()` methods

### Step 1: Audit & Fix Strategies
- [ ] Fix import errors and broken references in ensemble/multi_factor strategies
- [ ] Ensure each strategy implements the correct base class interface
- [ ] Verify data dependencies (what DataBus sources each strategy needs)

### Step 2: Register & Wire
- [ ] Register working strategies in `agents/config.py`
- [ ] Configure ensemble optimizer to combine Bittensor + technical signals
- [ ] Set conservative default weights (Bittensor: 0.4, Technical: 0.6)

### Step 3: Write Tests
- [ ] Test ensemble combines multiple strategy outputs correctly
- [ ] Test weight configuration
- [ ] Test fallback when one strategy has no data

### Step 4: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 5: Documentation & Delivery
- [ ] Document active strategies and their weights
- [ ] Discoveries logged

## Completion Criteria
- [ ] At least 3 strategies active (Bittensor + 2 technical)
- [ ] Ensemble produces combined signals
- [ ] Strategy weights configurable via env vars

## Git Commit Convention
- `feat(TP-008): complete Step N — description`

## Do NOT
- Delete any existing strategy files (fix or disable)
- Set aggressive default weights favoring any single strategy
- Enable live trading by default

---

## Amendments (Added During Execution)
