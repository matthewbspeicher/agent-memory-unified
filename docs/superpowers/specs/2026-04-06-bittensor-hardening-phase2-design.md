# Bittensor Hardening Phase 2 — Design Spec

**Date:** 2026-04-06
**Scope:** Testing, alerting, monitoring UI, API documentation
**Depends on:** Phase 1 (route registration, metrics, circuit breaker, multi-symbol, invite-only) — already merged to main.

---

## 1. InviteCode Feature Tests

**File:** `api/tests/Feature/InviteCodeTest.php`

**Prerequisites:**
- Fix `MagicLinkController.sendLink()` to throw `ValidationException::withMessages()` instead of `back()->withErrors()`. The SPA expects JSON 422 responses, not 302 redirects with session flash.

**Test cases (Pest + RefreshDatabase):**

| # | Scenario | Setup | Assert |
|---|----------|-------|--------|
| 1 | New user with valid invite | `InviteCode::generate()` -> use `$plainCode` | 302 redirect to check-email, user created, invite `times_used` incremented |
| 2 | Expired invite | code with `expires_at` in the past | 422, `invite_code` error message |
| 3 | Exhausted invite | code with `times_used >= max_uses` | 422, `invite_code` error message |
| 4 | New user without invite code | no `invite_code` param | 422, `invite_code` error message |
| 5 | Existing user without invite | user already in DB | 302 redirect (no invite needed) |

**Implementation notes:**
- Mock `Mail` facade to prevent email sends
- Use `InviteCode::generate()` which returns `[$invite, $plainCode]` — send `$plainCode` in POST, not `$invite->code_hash`
- `used_by_id` tracks last redeemer only — acceptable for single-use codes (the default)
- Success cases (1, 5) use `$this->post()` and assert 302 redirect (controller returns `redirect()`)
- Error cases (2, 3, 4) use `$this->postJson()` and assert 422 JSON with `errors.invite_code` (controller throws `ValidationException`)

---

## 2. CoinGecko Evaluator Alerting

**File:** `trading/integrations/bittensor/evaluator.py`

**Changes to `BittensorMetrics` (`models.py`):**
- Rename `windows_skipped_no_data` -> `windows_skipped`
- Add `last_skip_reason: str | None = None`

**Three skip paths in `_evaluate_window()` all get the same treatment:**

| Path | Current level | Reason string |
|------|--------------|---------------|
| No CoinGecko client or unmapped symbol | DEBUG -> WARNING | `"no_coingecko_or_unknown_symbol"` |
| No hash-verified forecasts for window | DEBUG -> WARNING | `"no_verified_forecasts"` |
| Insufficient candle data from CoinGecko | WARNING (keep) | `"insufficient_candle_data"` |

**For each path:**
1. `self.metrics.windows_skipped += 1`
2. `self.metrics.last_skip_reason = reason`
3. `await self._event_bus.publish("bittensor.evaluation_skipped", {"window_id": ..., "symbol": ..., "reason": reason})`
4. Log at WARNING level

**Metrics endpoint** (`/api/bittensor/metrics`) already exposes `BittensorMetrics` — `windows_skipped` and `last_skip_reason` will appear automatically once added to the dataclass.

---

## 3. Bittensor Status Page

**File:** `frontend/src/pages/BittensorNode.tsx` (rewrite of existing placeholder)

**Data sources:**
- `GET /api/bittensor/status` — scheduler, evaluator, miners, agent
- `GET /api/bittensor/metrics` — counters, durations, failure rates

**Layout (preserves existing GlassCard + Neural Mesh aesthetic):**

**Row 1 — Three GlassCards:**

| Card | Variant | Data |
|------|---------|------|
| Network / Scheduler | cyan | `enabled`, `healthy`, scheduler `running`, `next_window`, `windows_collected_total` |
| Evaluator | violet | `running`, `last_evaluation`, `unevaluated_windows`, `windows_evaluated_total`, `windows_skipped` |
| Weight Setter | green | `weight_sets_total`, `weight_sets_failed`, `last_weight_set_block` |

**Row 2 — Four compact metric cards:**

| Metric | Formula | Red threshold |
|--------|---------|--------------|
| Hash pass rate | `passed / (passed + failed)` guarded against `/0` | < 80% |
| Avg collection duration | `avg_collection_duration_secs` | > 120s |
| Miner response rate | `last_miner_response_rate` | < 50% |
| Consecutive failures | `consecutive_failures` | > 0 |

**Row 3 — Miner rankings table (replaces hardcoded terminal log):**
- Columns: hotkey (truncated), hybrid score, direction accuracy, windows evaluated
- Source: `status.miners.top_miners`
- Empty state: "No miners ranked yet"

**Behavior:**
- Auto-refresh via `useEffect` + `setInterval(30_000)`
- Loading skeleton on first fetch
- Optional chaining for missing subsystems: `metrics?.weight_setter?.weight_sets_total ?? 0`
- Uses existing `apiClient` fetch pattern from Gemini's refactored API layer

---

## 4. OpenAPI Docs for Bittensor Endpoints

**New file:** `trading/api/routes/bittensor_schemas.py`

**Response models (Pydantic v2 BaseModel):**

```
BittensorStatusResponse
  ├── enabled: bool
  ├── healthy: bool | None
  ├── scheduler: SchedulerStatus | None
  │     ├── running: bool
  │     ├── last_window_collected: str | None
  │     ├── next_window: str
  │     └── windows_collected_total: int
  ├── evaluator: EvaluatorStatus | None
  │     ├── running: bool
  │     ├── last_evaluation: str | None
  │     ├── unevaluated_windows: int
  │     └── windows_evaluated_total: int
  ├── miners: MinerSummary | None
  │     ├── total_in_metagraph: int
  │     ├── responded_last_window: int
  │     ├── response_rate: float
  │     └── top_miners: list[TopMinerItem]
  └── agent: AgentSummary | None
        ├── name: str
        ├── opportunities_emitted: int
        └── last_opportunity: str | None

BittensorMetricsResponse
  ├── enabled: bool
  ├── scheduler: SchedulerMetrics | None
  ├── evaluator: EvaluatorMetrics | None
  └── weight_setter: WeightSetterMetrics | None

BittensorRankingsResponse
  ├── rankings: list[MinerRankingItem]
  └── ranking_config: dict

MinerAccuracyResponse
  ├── hotkey: str
  └── records: list[AccuracyRecordItem]

BittensorSignalsResponse
  └── signals: list[dict]
```

**Route decorator changes:**
- Add `response_model=` to all 5 endpoints
- Add `response_model_exclude_none=True` to preserve existing wire format (omit null keys instead of sending explicit nulls)

**No behavior changes** — purely additive type annotations on existing return values.

---

## Files Changed Summary

| Service | File | Change |
|---------|------|--------|
| API | `app/Http/Controllers/Auth/MagicLinkController.php` | `back()->withErrors()` -> `ValidationException::withMessages()` |
| API | `tests/Feature/InviteCodeTest.php` | New — 5 test cases |
| Trading | `integrations/bittensor/models.py` | Rename metric, add `last_skip_reason` |
| Trading | `integrations/bittensor/evaluator.py` | Instrument 3 skip paths with metrics + events |
| Trading | `api/routes/bittensor_schemas.py` | New — Pydantic response models |
| Trading | `api/routes/bittensor.py` | Add `response_model=` to 5 endpoints |
| Frontend | `src/pages/BittensorNode.tsx` | Rewrite with live API data |
