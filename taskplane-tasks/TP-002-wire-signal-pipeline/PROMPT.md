# Task: TP-002 - Wire Signal Pipeline End-to-End

**Created:** 2026-04-07
**Size:** L

## Review Level: 2 (Plan and Code)

**Assessment:** Multi-component wiring across bridge, signal bus, aggregation, and strategy agents. Critical path for trading functionality.
**Score:** 5/8 — Blast radius: 2, Pattern novelty: 1, Security: 0, Reversibility: 2

## Canonical Task Folder

```
taskplane-tasks/TP-002-wire-signal-pipeline/
├── PROMPT.md
├── STATUS.md
└── .reviews/
```

## Mission

Wire the complete signal pipeline so miner positions from TaoshiBridge actually reach trading strategies and generate trade decisions. Currently there are THREE breaks in the pipeline:

1. **Signal type mismatch:** Bridge emits `bittensor_miner_position` but `BittensorAlphaAgent` listens for `bittensor_consensus`
2. **No aggregation layer:** Individual miner positions need to be aggregated into consensus signals before strategies can act
3. **No subscribers:** Nobody subscribes to bridge signals on the SignalBus

Build a `MinerConsensusAggregator` that subscribes to individual miner position signals, aggregates them into consensus views, and publishes `bittensor_consensus` signals that `BittensorAlphaAgent` already knows how to consume.

## Dependencies

- **Task:** TP-001 (bridge must emit signals for this to have data)

## Context to Read First

**Tier 2 (area context):**
- `taskplane-tasks/CONTEXT.md`

**Tier 3:**
- `CLAUDE.md` — architecture, signal bus description
- `trading/strategies/bittensor_consensus.py` — existing consumer (BittensorAlphaAgent)
- `trading/strategies/bittensor_signal.py` — existing BittensorSignalAgent for reference

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading container)

## File Scope

- `trading/integrations/bittensor/consensus_aggregator.py` (new)
- `trading/integrations/bittensor/taoshi_bridge.py` (minor — verify signal type)
- `trading/strategies/bittensor_consensus.py` (minor adjustments)
- `trading/api/app.py` (wire aggregator into lifespan)
- `trading/tests/unit/test_consensus_aggregator.py` (new)
- `trading/tests/integration/test_bittensor_e2e.py` (modified)

## Steps

### Step 0: Preflight

- [ ] Read the full signal flow: `taoshi_bridge.py` → `signal_bus.py` → `bittensor_consensus.py`
- [ ] Read `api/app.py` lifespan to understand where components are wired
- [ ] Read `agents/base.py` and `agents/runner.py` to understand how agents get their signal_bus reference
- [ ] Identify the exact signal types and payload schemas at each stage

### Step 1: Build MinerConsensusAggregator

Create `trading/integrations/bittensor/consensus_aggregator.py`:

- [ ] Class subscribes to SignalBus for `bittensor_miner_position` signals
- [ ] Maintains a sliding window of miner positions per symbol (configurable window, default 5 minutes)
- [ ] Aggregates into consensus: direction (bullish/bearish/flat based on majority), confidence (agreement ratio), expected_return (average leverage as proxy)
- [ ] Publishes `bittensor_consensus` signal to SignalBus when consensus changes or new window closes
- [ ] Handles edge cases: single miner, conflicting signals, stale data expiry
- [ ] Run targeted tests

**Artifacts:**
- `trading/integrations/bittensor/consensus_aggregator.py` (new)

### Step 2: Wire Into Application Lifespan

- [ ] In `api/app.py` lifespan, instantiate `MinerConsensusAggregator` with the shared `signal_bus`
- [ ] Ensure `BittensorAlphaAgent` gets the same `signal_bus` instance (verify it calls `setup()` which subscribes)
- [ ] Add aggregator status to the `/api/bittensor/status` endpoint
- [ ] Run targeted tests

**Artifacts:**
- `trading/api/app.py` (modified)
- `trading/api/routes/bittensor.py` (modified)

### Step 3: Write Tests

- [ ] Create `trading/tests/unit/test_consensus_aggregator.py`:
  - Single miner position → no consensus yet (below threshold)
  - Multiple miners same direction → consensus emitted
  - Mixed signals → low confidence consensus
  - Stale positions expire from window
  - Consensus payload matches what BittensorAlphaAgent expects
- [ ] Update `trading/tests/integration/test_bittensor_e2e.py` to test full pipeline

**Artifacts:**
- `trading/tests/unit/test_consensus_aggregator.py` (new)
- `trading/tests/integration/test_bittensor_e2e.py` (modified)

### Step 4: Testing & Verification

- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures
- [ ] Build passes

### Step 5: Documentation & Delivery

- [ ] Add docstrings to consensus_aggregator.py
- [ ] Update CONTEXT.md Known Issues
- [ ] Discoveries logged in STATUS.md

## Documentation Requirements

**Must Update:**
- `taskplane-tasks/CONTEXT.md` — update architecture diagram and known issues

**Check If Affected:**
- `CLAUDE.md` — architecture section if pipeline description changes

## Completion Criteria

- [ ] All steps complete
- [ ] All tests passing
- [ ] Full pipeline works: Bridge → SignalBus → Aggregator → SignalBus → BittensorAlphaAgent
- [ ] Consensus signals appear in `/api/bittensor/status`

## Git Commit Convention

- **Step completion:** `feat(TP-002): complete Step N — description`
- **Bug fixes:** `fix(TP-002): description`
- **Tests:** `test(TP-002): description`

## Do NOT

- Rewrite BittensorAlphaAgent from scratch — adapt the existing code
- Add real money trading logic — this is signal pipeline only
- Modify the TaoshiBridge signal format (TP-001 owns that)
- Add new pip dependencies without justification

---

## Amendments (Added During Execution)
