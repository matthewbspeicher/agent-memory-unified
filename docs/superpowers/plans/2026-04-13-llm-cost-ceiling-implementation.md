# LLM Cost Ceiling — Implementation Plan

**Date:** 2026-04-13
**Spec:** `docs/superpowers/specs/2026-04-13-llm-cost-ceiling-design.md`
**Estimated Effort:** 4-6 hours

## Task 1: Create CostLedger Module

**File:** `trading/llm/cost_ledger.py` (new)

### Steps

1. Create module with imports
2. Define `DEFAULT_COST_TABLE` (nested dict format)
3. Implement `CostLedger` class:
   - `__init__`: merge table, derive free providers, init Redis/local dict
   - `_merge_cost_table`: merge DEFAULT + JSON override
   - `_derive_free_providers`: compute free set from table
   - `_calculate_cost`: compute cost_cents from tokens
   - `record`: atomic INCRBYFLOAT + TTL + grace deadline
   - `get_global_spend`, `get_agent_spend`: read values
   - `get_cost`: lookup with provider/model/fallback
   - `get_breakdown`: scan agent keys for top agent
   - `should_block_paid`: check spend vs budget + grace
   - `check_thresholds`: return event type or None
   - `_maybe_set_grace_deadline`: idempotent deadline set
   - `_get_grace_deadline`: read deadline from Redis

### Acceptance Criteria

- [ ] Unit tests pass for cost calculation
- [ ] Redis pipeline atomicity verified
- [ ] In-memory fallback works when Redis=None
- [ ] Override JSON merges correctly
- [ ] Grace period logic correct (set once, read correctly)

---

## Task 2: Update LLMClient

**File:** `trading/llm/client.py` (modify)

### Steps

1. Add constructor params:
   ```python
   agent_name: str = "unknown"
   cost_ledger: CostLedger | None = None
   notifier: Notifier | None = None  # for cost alerts
   ```

2. Update `_resolve_chain()`:
   ```python
   def _resolve_chain(self) -> list[str]:
       chain = [p for p in self._chain if not self._is_disabled(p)]
       if self._cost_ledger and await self._cost_ledger.should_block_paid():
           chain = [p for p in chain if p in self._cost_ledger._free_providers]
       return chain or ["rule-based"]
   ```
   **Note:** `_resolve_chain` must become `async` or we check budget before calling it.

3. Update `complete()` — after `collector.record_call()`:
   ```python
   if self._cost_ledger:
       cost = await self._cost_ledger.record(
           self._agent_name, result.provider, result.model,
           result.input_tokens or 0, result.output_tokens or 0
       )
       event_type = await self._cost_ledger.check_thresholds()
       if event_type:
           await self._fire_cost_alert(event_type)
   ```

4. Update `chat()` — same pattern as `complete()`

5. Add helper `_fire_cost_alert()`:
   ```python
   async def _fire_cost_alert(self, event_type: str) -> None:
       if event_type in self._fired_alerts:
           return  # Session dedup (Redis dedup handles 24h)
       self._fired_alerts.add(event_type)
       from llm.cost_ledger import CostAlertData
       from notifications.cost import notify_cost_event
       breakdown = await self._cost_ledger.get_breakdown()
       data = CostAlertData(
           global_spend_cents=await self._cost_ledger.get_global_spend(),
           budget_cents=self._cost_ledger._config.daily_budget_cents,
           percent_used=...,
           top_agent=breakdown[0],
           top_agent_spend_cents=breakdown[1],
           provider_breakdown=breakdown[2],
           grace_deadline=await self._cost_ledger._get_grace_deadline(),
           window_reset_at=...,
       )
       await notify_cost_event(event_type, data, self._notifier)
   ```

### Design Decision: Sync vs Async _resolve_chain

**Problem:** Current `_resolve_chain()` is sync. Budget check requires async Redis call.

**Options:**
- A) Make `_resolve_chain()` async — requires updating all callers (complete, chat, score_headline, etc.)
- B) Check budget in caller before `_resolve_chain()` — extra check call
- C) Cache budget status in CostLedger (TTL-based) — check is sync

**Recommendation:** Option A — make `_resolve_chain()` async. It's called from async contexts already.

### Acceptance Criteria

- [ ] Constructor accepts agent_name and cost_ledger
- [ ] `_resolve_chain()` filters paid providers when over budget
- [ ] Cost recorded after successful LLM call
- [ ] Alerts fire at correct thresholds
- [ ] Existing tests still pass (backward compat)

---

## Task 3: Create Notification Helper

**File:** `trading/notifications/cost.py` (new)

### Steps

1. Define `CostAlertData` dataclass
2. Implement `notify_cost_event()`:
   - Structured log via `log_event()`
   - Optional notification dispatch via `notifier.send_text()`

### Acceptance Criteria

- [ ] Structured log emitted with correct event_type
- [ ] Notification sent if notifier configured
- [ ] Message format readable in Slack/Discord

---

## Task 4: Update Configuration

**File:** `trading/config.py` (modify)

### Steps

1. Add to `LLMConfig`:
   ```python
   daily_budget_cents: int = 500
   warning_threshold_pct: float = 0.80
   grace_period_minutes: int = 15
   cost_table_override: str | None = None
   ```

### Acceptance Criteria

- [ ] Env vars work: `STA_LLM_DAILY_BUDGET_CENTS`, etc.
- [ ] Flat accessor works: `config.daily_budget_cents`
- [ ] Default values match spec

---

## Task 5: Wire in app.py

**File:** `trading/api/app.py` (modify)

### Steps

1. Import CostLedger
2. In lifespan startup, after Redis init:
   ```python
   from llm.cost_ledger import CostLedger
   cost_ledger = CostLedger(redis=app.state.redis, config=config.llm)
   app.state.cost_ledger = cost_ledger
   ```
3. When creating LLMClient instances (for agents), pass cost_ledger and agent_name

### Acceptance Criteria

- [ ] CostLedger initialized with Redis connection
- [ ] LLMClient instances receive cost_ledger
- [ ] Agent names passed correctly

---

## Task 6: Unit Tests

**File:** `trading/tests/unit/test_llm/test_cost_ledger.py` (new)

### Test Cases

| Test | Description |
|------|-------------|
| `test_calculate_cost_anthropic` | Verify token → cents calculation |
| `test_calculate_cost_free` | Groq/Ollama = 0 cost |
| `test_calculate_cost_unknown_provider` | Unknown = 0 cost (fail-open) |
| `test_record_redis` | INCRBYFLOAT increments correctly |
| `test_record_in_memory` | Fallback when Redis=None |
| `test_record_zero_tokens` | Skip recording for zero tokens |
| `test_get_global_spend` | Returns accumulated value |
| `test_get_agent_spend` | Per-agent tracking works |
| `test_get_cost_lookup` | Provider/model → cost mapping |
| `test_get_cost_unknown` | Unknown provider returns zeros |
| `test_should_block_paid_under_80` | Returns False |
| `test_should_block_paid_over_100_no_grace` | Returns True |
| `test_should_block_paid_over_100_in_grace` | Returns False |
| `test_check_thresholds_warning` | 80-99% → "cost.warning" |
| `test_check_thresholds_ceiling` | 100% in grace → "cost.ceiling_hit" |
| `test_check_thresholds_blocked` | 100% grace expired → "cost.paid_blocked" |
| `test_grace_deadline_set_once` | Idempotent deadline setting |
| `test_ttl_on_keys` | Keys expire after 24h |
| `test_merge_cost_table_no_override` | Default table used |
| `test_merge_cost_table_with_override` | Override merges correctly |
| `test_derive_free_providers` | Groq, Ollama, rule-based are free |
| `test_get_breakdown` | Top agent identified correctly |

---

## Task 7: Integration Tests

**File:** `trading/tests/unit/test_llm/test_cost_integration.py` (new)

### Test Cases

| Test | Description |
|------|-------------|
| `test_chain_filtering_normal` | All providers returned when under budget |
| `test_chain_filtering_over_budget` | Only free providers when over budget |
| `test_chain_filtering_grace` | All providers during grace period |
| `test_cost_recorded_on_complete` | record() called after successful call |
| `test_cost_not_recorded_on_failure` | record() not called when provider fails |
| `test_alert_fired_at_warning` | Alert fires at 80% |
| `test_alert_fired_at_ceiling` | Alert fires at 100% |
| `test_alert_not_deduped_session` | Same alert doesn't fire twice in session |
| `test_agent_name_propagation` | Correct agent name in cost record |
| `test_rule_based_fallback_when_all_blocked` | Falls back to rule-based |

---

## Task 8: Documentation

**Files:** `CLAUDE.md` (modify)

### Steps

1. Add to "Key Modules":
   ```
   - `trading/llm/cost_ledger.py` — Redis-backed LLM cost tracking with per-agent spend
   ```

2. Add to "Always do":
   ```
   - **Check LLM cost budget** — If agents are looping, check `llm:cost:global` and `STA_LLM_DAILY_BUDGET_CENTS`
   ```

---

## Execution Order

```
1. Task 1 (CostLedger) ← Foundation
2. Task 4 (Config) ← Required by Task 1
3. Task 3 (Notifications) ← Required by Task 2
4. Task 2 (LLMClient) ← Depends on 1, 3, 4
5. Task 5 (app.py wiring) ← Depends on 1, 2
6. Task 6 (Unit tests) ← Can run in parallel with 2-5
7. Task 7 (Integration tests) ← After 2, 5 complete
8. Task 8 (Docs) ← Final
```

### Parallel Execution

- Tasks 1, 3, 4 can run in parallel (no dependencies)
- Task 2 waits for 1, 3, 4
- Task 5 waits for 1, 2
- Tasks 6, 7 can be developed in parallel with implementation

---

## Rollback Plan

If issues arise:

1. **Immediate:** Set `STA_LLM_DAILY_BUDGET_CENTS=999999` to effectively disable
2. **Code revert:** CostLedger is additive; revert `client.py` changes to restore original `_resolve_chain()`
3. **Full rollback:** Remove `cost_ledger` param from LLMClient constructor

---

## Verification Checklist

After implementation:

- [ ] `cd trading && python -m pytest tests/unit/test_llm/ -v --tb=short`
- [ ] Manual test: set budget to $0.01, trigger LLM call, verify rule-based fallback
- [ ] Check Redis keys: `redis-cli keys "llm:cost:*"` after LLM calls
- [ ] Verify alert fires: set budget low, watch logs for `cost.warning` event
- [ ] Verify TTL: `redis-cli ttl llm:cost:global` should be ~86400
