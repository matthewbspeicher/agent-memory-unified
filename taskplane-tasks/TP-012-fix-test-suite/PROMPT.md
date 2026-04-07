# Task: TP-012 - Fix Test Suite

**Created:** 2026-04-07
**Size:** M

## Review Level: 1 (Plan Only)

**Assessment:** Test infrastructure fix. No production code changes, just making tests runnable.
**Score:** 2/8 — Blast radius: 1, Pattern novelty: 0, Security: 0, Reversibility: 1

## Canonical Task Folder

```
taskplane-tasks/TP-012-fix-test-suite/
```

## Mission

Fix the trading engine test suite so it runs reliably. Currently `python -m pytest` fails due to missing dependencies in the Docker container (pytest not installed via uv) and likely import errors from refactored modules (the dead evaluator/weight-setter were removed but tests may still reference them). Get to a green baseline.

## Dependencies

- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:**
- `CLAUDE.md` — testing commands
- `trading/pyproject.toml` — dependency management

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading, postgres, redis)

## File Scope

- `trading/pyproject.toml` (ensure pytest in dev deps)
- `trading/tests/**/*.py` (fix broken imports/references)
- `Dockerfile.trading` (ensure test deps installable)
- `trading/conftest.py` or `trading/tests/conftest.py`

## Steps

### Step 0: Preflight
- [ ] Try running tests: `docker exec agent-memory-unified-trading-1 python -m pytest tests/ --co -q`
- [ ] Identify: missing packages, import errors, removed module references
- [ ] Read pyproject.toml for dependency groups

### Step 1: Fix Test Infrastructure
- [ ] Ensure pytest and test dependencies are installed in Docker container
- [ ] Fix conftest.py fixtures if broken
- [ ] Add a `make test` or script shortcut for running tests

### Step 2: Fix Broken Tests
- [ ] Remove/update tests referencing deleted evaluator and weight_setter modules
- [ ] Fix import errors from refactored modules
- [ ] Mark flaky/integration tests that need live services with `@pytest.mark.integration`
- [ ] Skip tests requiring IBKR connection with `@pytest.mark.skipif`

### Step 3: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Achieve ≥90% pass rate (remaining failures must be tracked as known issues)
- [ ] Document any skipped tests and their reasons

### Step 4: Documentation & Delivery
- [ ] Update CLAUDE.md testing section with working commands
- [ ] Discoveries logged

## Completion Criteria
- [ ] `python -m pytest tests/` runs without infrastructure errors
- [ ] All unit tests pass
- [ ] Integration tests either pass or are properly skipped with markers

## Git Commit Convention
- `fix(TP-012): complete Step N — description`

## Do NOT
- Delete tests that test valid functionality (fix them instead)
- Add `xfail` to hide real failures (use `skip` with reason for infrastructure issues only)
- Modify production code to make tests pass (fix the tests)

---

## Amendments (Added During Execution)
