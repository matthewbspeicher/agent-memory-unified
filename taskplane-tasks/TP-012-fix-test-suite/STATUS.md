# TP-012: Fix Test Suite — Status

**Current Step:** Step 4: Documentation & Delivery
**Status:** ✅ Complete
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
**Status:** ✅ Complete

- [x] Fix config tests: add env var isolation so container STA_ vars don't leak
- [x] Fix adapter retry tests: update mock to match v10 API (capitalized Subtensor)
- [x] Fix optimizer tests: schema already correct in worktree (container was stale)
- [x] Fix backtest API tests: same schema issue (db.py was stale in container)
- [x] Fix journal indexer test: mock encode() now returns correct 2D shape

---

### Step 3: Testing & Verification
**Status:** ✅ Complete

- [x] Run unit test suite with --timeout=30 — 1664 passed, 0 failed, 2 deselected
- [x] Verify ≥90% pass rate — 100% pass rate
- [x] Document skipped tests: test_app_startup (2 tests) marked @pytest.mark.integration (need Redis + agent framework)

---

### Step 4: Documentation & Delivery
**Status:** ✅ Complete

- [x] Update CLAUDE.md testing section
- [x] Log discoveries

---

## Reviews
| # | Type | Step | Verdict | File |
|---|------|------|---------|------|

## Discoveries
| Discovery | Disposition | Location |
|-----------|-------------|----------|
| Docker volume mounts main repo, not worktree — tests in container see stale files | Workaround: docker cp for testing | trading/storage/db.py |
| Config tests need env isolation in Docker (STA_ vars from .env) | Fixed with monkeypatch | tests/test_config*.py |
| test_app_startup starts full app (Redis, agents) — not a true unit test | Marked @pytest.mark.integration | tests/unit/test_api/test_app_startup.py |
| Adapter retry tests mocked bt.subtensor (v9) but adapter uses bt.Subtensor (v10) | Fixed mocks | tests/unit/test_integrations/test_bittensor_adapter_retry.py |

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
