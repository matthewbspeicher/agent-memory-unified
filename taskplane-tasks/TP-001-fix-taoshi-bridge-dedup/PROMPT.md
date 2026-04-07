# Task: TP-001 - Fix TaoshiBridge Change Detection

**Created:** 2026-04-07
**Size:** M

## Review Level: 2 (Plan and Code)

**Assessment:** Core data pipeline fix affecting all downstream strategies. Wrong dedup logic silently drops all position updates after first scan.
**Score:** 4/8 — Blast radius: 1, Pattern novelty: 1, Security: 0, Reversibility: 2

## Canonical Task Folder

```
taskplane-tasks/TP-001-fix-taoshi-bridge-dedup/
├── PROMPT.md
├── STATUS.md
└── .reviews/
```

## Mission

Fix the TaoshiBridge so that position **updates** (new orders, leverage changes) flow through as new signals. Currently `_seen_position_uuids` is a grow-only set — once a UUID is seen on the first poll, it's never re-emitted even when new orders are added to the position.

**Note:** A parallel conductor track ("Scoring Continuity") is adding DB-backed persistence for the seen set. This task focuses ONLY on **change detection** — making the bridge detect when a position has been updated. The change detection logic must work with both in-memory tracking (current) and future DB-backed tracking. Do NOT add database persistence — that's the conductor track's scope.

## Dependencies

- **None**

## Context to Read First

**Tier 2 (area context):**
- `taskplane-tasks/CONTEXT.md`

**Tier 3:**
- `CLAUDE.md` — architecture overview, bridge description
- `conductor/tracks/scoring_continuity_20260407/spec.md` — parallel work to be aware of (do NOT implement their scope)

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading container)

## File Scope

- `trading/integrations/bittensor/taoshi_bridge.py`
- `trading/tests/unit/test_taoshi_bridge.py` (new)
- `trading/tests/integration/test_bittensor_e2e.py` (modified)

## Steps

### Step 0: Preflight

- [ ] Read `trading/integrations/bittensor/taoshi_bridge.py` fully
- [ ] Examine sample position files in `taoshi-vanta/validation/miners/` to understand data format (order arrays, timestamps)
- [ ] Read `conductor/tracks/scoring_continuity_20260407/spec.md` to understand parallel work scope
- [ ] Read existing test patterns in `trading/tests/integration/test_bittensor_e2e.py`

### Step 1: Implement Change Detection

Replace the simple UUID set with hash-based change tracking:

- [ ] Replace `_seen_position_uuids: set[str]` with `_seen_positions: dict[str, str]` mapping `{uuid: content_hash}`
- [ ] Add `_hash_position(position: dict) -> str` — hash based on order count + latest order timestamp + latest leverage
- [ ] Emit signal when: (a) UUID is new, OR (b) UUID exists but hash changed
- [ ] Include `signal_reason` in payload: `"new_position"` or `"position_updated"`
- [ ] Include `order_count` in payload
- [ ] Clean up entries for positions no longer found on disk (moved to `closed/`)
- [ ] Update `get_status()` to report `updates_detected` counter
- [ ] Run targeted tests

**Artifacts:**
- `trading/integrations/bittensor/taoshi_bridge.py` (modified)

### Step 2: Write Tests

- [ ] Create `trading/tests/unit/test_taoshi_bridge.py` with:
  - New position UUID emits signal with reason `new_position`
  - Same position with no changes does NOT re-emit
  - Position with new order DOES re-emit with reason `position_updated`
  - Closed/removed position gets cleaned from tracking dict
  - `_hash_position` produces different hashes for different order states
- [ ] Update `trading/tests/integration/test_bittensor_e2e.py` if it references bridge behavior

**Artifacts:**
- `trading/tests/unit/test_taoshi_bridge.py` (new)
- `trading/tests/integration/test_bittensor_e2e.py` (modified if needed)

### Step 3: Testing & Verification

- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Fix all failures
- [ ] Build passes

### Step 4: Documentation & Delivery

- [ ] Update docstring in `taoshi_bridge.py` explaining change-detection logic
- [ ] Discoveries logged in STATUS.md

## Documentation Requirements

**Must Update:**
- `trading/integrations/bittensor/taoshi_bridge.py` — docstring

**Check If Affected:**
- `taskplane-tasks/CONTEXT.md` — update Known Issues if fixed

## Completion Criteria

- [ ] All steps complete
- [ ] All tests passing
- [ ] Bridge emits signals for position updates, not just new positions
- [ ] No memory leak from growing tracking dict
- [ ] Compatible with future DB-backed persistence (clean interface)

## Git Commit Convention

- **Step completion:** `feat(TP-001): complete Step N — description`
- **Bug fixes:** `fix(TP-001): description`
- **Tests:** `test(TP-001): description`
- **Hydration:** `hydrate: TP-001 expand Step N checkboxes`

## Do NOT

- Add database persistence for the seen set (that's the conductor track's scope)
- Change the `AgentSignal` schema — that's TP-002's scope
- Modify `SignalBus` behavior
- Add new pip dependencies
- Skip writing tests

---

## Amendments (Added During Execution)
