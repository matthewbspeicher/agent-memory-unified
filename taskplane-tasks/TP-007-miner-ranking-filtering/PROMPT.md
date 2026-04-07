# Task: TP-007 - Miner Ranking & Signal Filtering

**Created:** 2026-04-07
**Size:** L

## Review Level: 2 (Plan and Code)

**Assessment:** New scoring system that directly affects trading quality. Historical accuracy tracking with data model changes.
**Score:** 5/8 — Blast radius: 1, Pattern novelty: 2, Security: 0, Reversibility: 2

## Canonical Task Folder

```
taskplane-tasks/TP-007-miner-ranking-filtering/
```

## Mission

Build a lightweight miner scoring system that tracks historical accuracy of miner signals and uses scores to weight their input in consensus aggregation. The original evaluator was removed (`refactor(trading): remove dead evaluator`), so this is a fresh implementation. Track each miner's signal accuracy over time and use this to filter low-quality miners and weight high-quality ones in the consensus.

**Note:** Gemini's conductor track may also touch the evaluator space. This task focuses on a lightweight scoring approach that works independently — tracking signal outcomes (did the predicted direction match actual price movement?).

## Dependencies

- **None**
- **External:** PostgreSQL running

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `CLAUDE.md` — evaluator history
- `conductor/tracks/scoring_continuity_20260407/spec.md` — parallel work awareness

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading, postgres)

## File Scope

- `trading/integrations/bittensor/miner_scorer.py` (new)
- `trading/integrations/bittensor/consensus_aggregator.py` (modified — use scores)
- `scripts/init-trading-tables.sql` (add scoring tables)
- `trading/api/routes/bittensor.py` (add rankings endpoint)
- `trading/tests/unit/test_miner_scorer.py` (new)

## Steps

### Step 0: Preflight
- [ ] Read removed evaluator code from git history for patterns
- [ ] Read consensus_aggregator.py (from TP-002)
- [ ] Read existing DB schema in `scripts/init-trading-tables.sql`

### Step 1: Create Scoring Tables
- [ ] Add `miner_signal_history` table: hotkey, symbol, predicted_direction, actual_direction, signal_time, evaluation_time, correct (bool)
- [ ] Add `miner_scores` table: hotkey, symbol, accuracy_7d, accuracy_30d, total_signals, last_updated
- [ ] Add to `scripts/init-trading-tables.sql`

### Step 2: Implement MinerScorer
- [ ] Create `trading/integrations/bittensor/miner_scorer.py`
- [ ] Record each miner signal with predicted direction
- [ ] Periodic evaluation job: compare predicted vs actual price movement after N minutes
- [ ] Calculate rolling accuracy scores (7d, 30d windows)
- [ ] Expose `get_miner_weight(hotkey, symbol) -> float` for consensus aggregator

### Step 3: Integrate with Consensus Aggregator
- [ ] Modify consensus aggregator to fetch miner weights from scorer
- [ ] Weight miner signals by accuracy score in consensus calculation
- [ ] Filter miners below minimum accuracy threshold (configurable)
- [ ] Add miner rankings to `/api/bittensor/rankings` endpoint

### Step 4: Write Tests
- [ ] Test scoring calculation with known signal histories
- [ ] Test weight integration in consensus
- [ ] Test low-accuracy miner filtering

### Step 5: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures

### Step 6: Documentation & Delivery
- [ ] Document scoring methodology
- [ ] Discoveries logged

## Completion Criteria
- [ ] Miner signals tracked and scored
- [ ] Consensus aggregation weighted by miner quality
- [ ] Rankings visible via API endpoint

## Git Commit Convention
- `feat(TP-007): complete Step N — description`

## Do NOT
- Duplicate Gemini's evaluator work (check conductor track state first)
- Set weights on-chain (that's validator scope)
- Add complex ML models — keep scoring simple (accuracy ratio)

---

## Amendments (Added During Execution)
