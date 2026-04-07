# TP-012: Fix Test Suite — Status

**Current Step:** Step 1: Fix Test Infrastructure
**Status:** 🟡 In Progress
**Last Updated:** 2026-04-07
**Review Level:** 1
**Review Counter:** 0
**Iteration:** 1
**Size:** S
M

---

### Step 0: Preflight
**Status:** ✅ Complete

- [x] Run test collection and full suite to identify failures
- [x] Categorize failures and document in notes

---

### Step 1: Fix Test Infrastructure
**Status:** ✅ Complete

- [x] Ensure pytest + pytest-asyncio in dev deps and installable in Docker
- [x] Add pytest-timeout to dev deps for hanging test protection
- [x] Add Makefile test target or verify existing test scripts

---

### Step 2: Fix Broken Tests
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Complete step objectives

---

### Step 3: Testing & Verification
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Complete step objectives

---

### Step 4: Documentation & Delivery
**Status:** ⬜ Not Started

> ⚠️ Hydrate: Expand checkboxes when entering this step

- [ ] Complete step objectives

---

## Reviews
| # | Type | Step | Verdict | File |
|---|------|------|---------|------|

## Discoveries
| Discovery | Disposition | Location |
|-----------|-------------|----------|

## Execution Log
| Timestamp | Action | Outcome |
|-----------|--------|---------|
| 2026-04-07 | Task staged | PROMPT.md and STATUS.md created |
| 2026-04-07 17:18 | Task started | Runtime V2 lane-runner execution |
| 2026-04-07 17:18 | Step 0 started | Preflight |

## Blockers
*None*

## Notes
13 failures / 1706 passed / 4 skipped / 21 deselected

**Failure categories:**
1. **Config env leak (5 tests)**: `load_config(env_file="/dev/null")` picks up real STA_ env vars from container. Tests need `monkeypatch.delenv` or `os.environ` cleanup.
   - test_config.py::TestLoadConfigFromDotEnv::test_reads_dotenv_file (api_port=8080 vs expected 9000)
   - test_config_bittensor.py (2 tests) — bittensor.enabled=True vs expected False
   - test_config_nested.py (2 tests) — same issue
2. **Adapter retry mock mismatch (2 tests)**: Mocks patch `bt.subtensor` (lowercase) but adapter uses `getattr(bt, 'Subtensor', None)` which returns truthy MagicMock, so the lowercase mock_subtensor is never called.
   - test_bittensor_adapter_retry.py (2 tests)
3. **Schema mismatch (5 tests)**: optimizer.save_result writes `data_start` column that doesn't exist in test DDL.
   - test_optimizer.py (3 tests)
   - test_backtest_api.py (2 tests)
4. **hnswlib dimension bug (1 test)**: test_indexer.py::test_rehydrate_indexes_entries — vector shape mismatch in hnswlib add_items
