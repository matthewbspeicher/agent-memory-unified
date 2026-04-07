# Task: TP-005 - Structured Logging

**Created:** 2026-04-07
**Size:** M

## Review Level: 1 (Plan Only)

**Assessment:** Cross-cutting concern but low risk. Replaces debug spam with structured output.
**Score:** 2/8 — Blast radius: 1, Pattern novelty: 1, Security: 0, Reversibility: 0

## Canonical Task Folder

```
taskplane-tasks/TP-005-structured-logging/
```

## Mission

Replace the noisy DEBUG-level logging throughout the trading engine with structured, leveled logging. The TaoshiBridge currently emits a debug log every 30 seconds ("no new signals") which drowns out meaningful events. Implement structured JSON logging with clear event types so signal events, trade decisions, and errors are visible without noise.

## Dependencies

- **None**

## Context to Read First

**Tier 2:** `taskplane-tasks/CONTEXT.md`
**Tier 3:** `CLAUDE.md` — architecture overview

## Environment

- **Workspace:** `trading/`
- **Services required:** Docker (trading)

## File Scope

- `trading/utils/logging.py` (new)
- `trading/integrations/bittensor/taoshi_bridge.py` (logging updates)
- `trading/api/app.py` (logging setup)
- `trading/config.py` (log level config)
- `trading/strategies/*.py` (logging updates)

## Steps

### Step 0: Preflight
- [ ] Audit current logging patterns across trading/
- [ ] Identify the noisiest log sources

### Step 1: Create Logging Infrastructure
- [ ] Create `trading/utils/logging.py` with structured JSON formatter
- [ ] Support event types: `signal.received`, `signal.consensus`, `trade.decision`, `trade.executed`, `bridge.poll`, `bridge.signal`, `error`
- [ ] Add `STA_LOG_LEVEL` and `STA_LOG_FORMAT` (json|text) config options
- [ ] Configure root logger in app startup

### Step 2: Update Key Modules
- [ ] TaoshiBridge: reduce poll log to TRACE/suppress, keep signal emission at INFO
- [ ] SignalBus: log publish events at INFO with signal_type
- [ ] BittensorAlphaAgent: log trade decisions at INFO
- [ ] API routes: log request handling at DEBUG

### Step 3: Testing & Verification
- [ ] Run FULL test suite: `cd trading && python -m pytest tests/ -v --tb=short`
- [ ] Verify Docker logs show clean structured output
- [ ] Fix all failures

### Step 4: Documentation & Delivery
- [ ] Document log format and config in CLAUDE.md
- [ ] Discoveries logged

## Documentation Requirements
**Must Update:** `CLAUDE.md` — add logging configuration section
**Check If Affected:** `docker-compose.yml` — may need env vars

## Completion Criteria
- [ ] Trading logs are clean and structured
- [ ] Signal events clearly visible without grep
- [ ] Log level configurable via env var

## Git Commit Convention
- `feat(TP-005): complete Step N — description`

## Do NOT
- Add heavy logging dependencies (structlog ok, but prefer stdlib)
- Change log output format for tests (tests may parse logs)
- Remove any ERROR/WARNING level logs

---

## Amendments (Added During Execution)
