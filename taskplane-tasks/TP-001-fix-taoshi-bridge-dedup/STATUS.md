# TP-001: Fix TaoshiBridge Change Detection — Status

**Current Step:** Not Started
**Status:** 🔵 Ready for Execution
**Last Updated:** 2026-04-07
**Review Level:** 2
**Review Counter:** 0
**Iteration:** 0
**Size:** M

---

### Step 0: Preflight
**Status:** ⬜ Not Started

- [ ] Read bridge source fully
- [ ] Examine position file format
- [ ] Read conductor track spec (awareness only)
- [ ] Read existing test patterns

---

### Step 1: Implement Change Detection
**Status:** ⬜ Not Started

- [ ] Replace set with hash-tracking dict
- [ ] Add `_hash_position` helper
- [ ] Emit signals for new AND updated positions
- [ ] Add `signal_reason` and `order_count` to payload
- [ ] Clean up closed positions from tracking
- [ ] Update `get_status()` with new counters

---

### Step 2: Write Tests
**Status:** ⬜ Not Started

- [ ] Create `test_taoshi_bridge.py` with 5+ test cases
- [ ] Update e2e test if needed

---

### Step 3: Testing & Verification
**Status:** ⬜ Not Started

- [ ] FULL test suite passing
- [ ] All failures fixed

---

### Step 4: Documentation & Delivery
**Status:** ⬜ Not Started

- [ ] Update docstrings
- [ ] Discoveries logged

---

## Reviews

| # | Type | Step | Verdict | File |
|---|------|------|---------|------|

---

## Discoveries

| Discovery | Disposition | Location |
|-----------|-------------|----------|

---

## Execution Log

| Timestamp | Action | Outcome |
|-----------|--------|---------|
| 2026-04-07 | Task staged | PROMPT.md and STATUS.md created |

---

## Blockers

*None*

---

## Notes

Parallel work: Gemini conductor track "Scoring Continuity" is adding DB persistence for the seen set. This task only adds change detection logic.
