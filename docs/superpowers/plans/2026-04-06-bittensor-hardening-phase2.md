# Bittensor Hardening Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add invite-code tests, evaluator skip alerting, live Bittensor status page, and OpenAPI docs for Bittensor endpoints.

**Architecture:** Four independent changes across the API (Laravel/PHP), Trading (Python/FastAPI), and Frontend (React/TS) services. Shared BittensorMetrics dataclass is the bridge between backend instrumentation and frontend display.

**Tech Stack:** Pest (PHP tests), FastAPI + Pydantic (OpenAPI schemas), React + axios + GlassCard (status page)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `api/app/Http/Controllers/Auth/MagicLinkController.php` | Fix 302 -> 422 for SPA error handling |
| Create | `api/tests/Feature/InviteCodeTest.php` | 5 test cases for invite-gated registration |
| Modify | `trading/integrations/bittensor/models.py` | Rename metric field, add `last_skip_reason` |
| Modify | `trading/integrations/bittensor/evaluator.py` | Instrument 3 skip paths |
| Modify | `trading/api/routes/bittensor.py` | Add response_model to 5 endpoints, update metrics key |
| Create | `trading/api/routes/bittensor_schemas.py` | Pydantic response models for OpenAPI |
| Rewrite | `frontend/src/pages/BittensorNode.tsx` | Live status page consuming API data |

---

### Task 1: Fix MagicLinkController 302 -> ValidationException

**Files:**
- Modify: `api/app/Http/Controllers/Auth/MagicLinkController.php:1-102`

- [ ] **Step 1: Add ValidationException import and replace back()->withErrors()**

In `api/app/Http/Controllers/Auth/MagicLinkController.php`, add the import and replace the two `back()->withErrors()` calls:

```php
// Add to imports (after the existing use statements):
use Illuminate\Validation\ValidationException;

// Replace line 35:
//   return back()->withErrors(['invite_code' => 'An invite code is required to create a new account.']);
// With:
throw ValidationException::withMessages([
    'invite_code' => 'An invite code is required to create a new account.',
]);

// Replace line 40:
//   return back()->withErrors(['invite_code' => 'Invalid or expired invite code.']);
// With:
throw ValidationException::withMessages([
    'invite_code' => 'Invalid or expired invite code.',
]);
```

- [ ] **Step 2: Verify syntax**

Run: `php -l api/app/Http/Controllers/Auth/MagicLinkController.php`
Expected: `No syntax errors detected`

- [ ] **Step 3: Commit**

```bash
git add api/app/Http/Controllers/Auth/MagicLinkController.php
git commit -m "fix(auth): throw ValidationException for JSON 422 responses in invite flow"
```

---

### Task 2: InviteCode Feature Tests

**Files:**
- Create: `api/tests/Feature/InviteCodeTest.php`

- [ ] **Step 1: Write all 5 test cases**

Create `api/tests/Feature/InviteCodeTest.php`:

```php
<?php

use App\Models\InviteCode;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Mail;

uses(RefreshDatabase::class);

beforeEach(function () {
    Mail::fake();
});

describe('POST /login — invite-gated registration', function () {

    it('creates a new user with a valid invite code', function () {
        [$invite, $plainCode] = InviteCode::generate(label: 'test');

        $response = $this->post('/login', [
            'name' => 'New User',
            'email' => 'newuser@example.com',
            'invite_code' => $plainCode,
        ]);

        $response->assertRedirect();

        $this->assertDatabaseHas('users', ['email' => 'newuser@example.com']);

        $invite->refresh();
        expect($invite->times_used)->toBe(1);
        expect($invite->used_by_id)->not->toBeNull();
    });

    it('rejects an expired invite code with 422', function () {
        [$invite, $plainCode] = InviteCode::generate(
            label: 'expired',
            expiresAt: now()->subDay(),
        );

        $response = $this->postJson('/login', [
            'name' => 'Should Fail',
            'email' => 'expired@example.com',
            'invite_code' => $plainCode,
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['invite_code']);

        $this->assertDatabaseMissing('users', ['email' => 'expired@example.com']);
    });

    it('rejects an exhausted invite code with 422', function () {
        [$invite, $plainCode] = InviteCode::generate(label: 'used-up', maxUses: 1);
        $invite->update(['times_used' => 1]);

        $response = $this->postJson('/login', [
            'name' => 'Should Fail',
            'email' => 'exhausted@example.com',
            'invite_code' => $plainCode,
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['invite_code']);

        $this->assertDatabaseMissing('users', ['email' => 'exhausted@example.com']);
    });

    it('rejects a new user without an invite code with 422', function () {
        $response = $this->postJson('/login', [
            'name' => 'No Code',
            'email' => 'nocode@example.com',
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors(['invite_code']);

        $this->assertDatabaseMissing('users', ['email' => 'nocode@example.com']);
    });

    it('allows an existing user to log in without an invite code', function () {
        User::factory()->create(['email' => 'existing@example.com']);

        $response = $this->post('/login', [
            'name' => 'Existing User',
            'email' => 'existing@example.com',
        ]);

        $response->assertRedirect();
    });
});
```

- [ ] **Step 2: Run tests**

Run: `cd api && php artisan test tests/Feature/InviteCodeTest.php`
Expected: 5 tests pass (green)

- [ ] **Step 3: Commit**

```bash
git add api/tests/Feature/InviteCodeTest.php
git commit -m "test(auth): add invite code feature tests for gated registration"
```

---

### Task 3: CoinGecko Evaluator Skip Alerting

**Files:**
- Modify: `trading/integrations/bittensor/models.py:163-192`
- Modify: `trading/integrations/bittensor/evaluator.py:173-207`
- Modify: `trading/api/routes/bittensor.py:202-210`

- [ ] **Step 1: Update BittensorMetrics dataclass**

In `trading/integrations/bittensor/models.py`, replace `windows_skipped_no_data` and add `last_skip_reason`:

```python
# Replace line 179:
#     windows_skipped_no_data: int = 0
# With:
    windows_skipped: int = 0
    last_skip_reason: str | None = None
```

- [ ] **Step 2: Instrument all three skip paths in evaluator**

In `trading/integrations/bittensor/evaluator.py`, replace the first skip path (lines 176-184):

```python
    async def _evaluate_window(self, window) -> None:
        """Fetch realized bars and compute per-miner accuracy for one window."""
        eval_start = datetime.now(tz=timezone.utc)
        if self._coingecko is None or window.symbol not in SYMBOL_TO_COINGECKO:
            reason = "no_coingecko_or_unknown_symbol"
            self.metrics.windows_skipped += 1
            self.metrics.last_skip_reason = reason
            logger.warning(
                "BittensorEvaluator: skipping window %s — %s (symbol=%s)",
                window.window_id,
                reason,
                window.symbol,
            )
            await self._event_bus.publish(
                "bittensor.evaluation_skipped",
                {"window_id": window.window_id, "symbol": window.symbol, "reason": reason},
            )
            return
```

Replace the second skip path (lines 186-192 — no verified forecasts):

```python
        all_forecasts = await self._store.get_raw_forecasts_by_window(window.window_id)
        forecasts = [f for f in all_forecasts if getattr(f, "hash_verified", True)]
        if not forecasts:
            reason = "no_verified_forecasts"
            self.metrics.windows_skipped += 1
            self.metrics.last_skip_reason = reason
            logger.warning(
                "BittensorEvaluator: skipping window %s — %s",
                window.window_id,
                reason,
            )
            await self._event_bus.publish(
                "bittensor.evaluation_skipped",
                {"window_id": window.window_id, "symbol": window.symbol, "reason": reason},
            )
            return
```

Replace the third skip path (lines 199-207 — insufficient candles):

```python
        if len(realized) < window.prediction_size * 0.9:
            reason = "insufficient_candle_data"
            self.metrics.windows_skipped += 1
            self.metrics.last_skip_reason = reason
            logger.warning(
                "BittensorEvaluator: skipping window %s — %s (got %d, need ~%d)",
                window.window_id,
                reason,
                len(realized),
                window.prediction_size,
            )
            await self._event_bus.publish(
                "bittensor.evaluation_skipped",
                {"window_id": window.window_id, "symbol": window.symbol, "reason": reason},
            )
            return
```

- [ ] **Step 3: Update metrics endpoint to use renamed field**

In `trading/api/routes/bittensor.py`, update the evaluator metrics block (lines 205-209):

```python
        result["evaluator"] = {
            "windows_evaluated": m.windows_evaluated,
            "windows_expired": m.windows_expired,
            "windows_skipped": m.windows_skipped,
            "last_skip_reason": m.last_skip_reason,
            "last_evaluation_duration_secs": round(m.last_evaluation_duration_secs, 2),
        }
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['integrations/bittensor/models.py', 'integrations/bittensor/evaluator.py', 'api/routes/bittensor.py']]; print('OK')"` from the `trading/` directory.
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add trading/integrations/bittensor/models.py trading/integrations/bittensor/evaluator.py trading/api/routes/bittensor.py
git commit -m "feat(bittensor): add alerting for evaluation skip paths with metrics and events"
```

---

### Task 4: OpenAPI Schemas for Bittensor Endpoints

**Files:**
- Create: `trading/api/routes/bittensor_schemas.py`
- Modify: `trading/api/routes/bittensor.py:1-10,13,113,144,176,224`

- [ ] **Step 1: Create Pydantic response models**

Create `trading/api/routes/bittensor_schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


# --- /api/bittensor/status ---

class SchedulerStatus(BaseModel):
    running: bool
    last_window_collected: str | None = None
    next_window: str
    windows_collected_total: int


class EvaluatorStatus(BaseModel):
    running: bool
    last_evaluation: str | None = None
    unevaluated_windows: int
    windows_evaluated_total: int


class TopMinerItem(BaseModel):
    hotkey: str
    hybrid_score: float
    direction_accuracy: float
    windows_evaluated: int


class MinerSummary(BaseModel):
    total_in_metagraph: int
    responded_last_window: int
    response_rate: float
    top_miners: list[TopMinerItem]


class AgentSummary(BaseModel):
    name: str
    opportunities_emitted: int
    last_opportunity: str | None = None


class BittensorStatusResponse(BaseModel):
    enabled: bool
    healthy: bool | None = None
    scheduler: SchedulerStatus | None = None
    evaluator: EvaluatorStatus | None = None
    miners: MinerSummary | None = None
    agent: AgentSummary | None = None


# --- /api/bittensor/metrics ---

class SchedulerMetrics(BaseModel):
    windows_collected: int
    windows_failed: int
    hash_verifications_passed: int
    hash_verifications_failed: int
    last_collection_duration_secs: float
    avg_collection_duration_secs: float
    last_miner_response_rate: float
    consecutive_failures: int


class EvaluatorMetrics(BaseModel):
    windows_evaluated: int
    windows_expired: int
    windows_skipped: int
    last_skip_reason: str | None = None
    last_evaluation_duration_secs: float


class WeightSetterMetrics(BaseModel):
    weight_sets_total: int
    weight_sets_failed: int
    last_weight_set_block: int | None = None


class BittensorMetricsResponse(BaseModel):
    enabled: bool
    scheduler: SchedulerMetrics | None = None
    evaluator: EvaluatorMetrics | None = None
    weight_setter: WeightSetterMetrics | None = None


# --- /api/bittensor/rankings ---

class MinerRankingItem(BaseModel):
    miner_hotkey: str
    hybrid_score: float
    direction_accuracy: float
    mean_magnitude_error: float
    mean_path_correlation: float | None = None
    internal_score: float
    latest_incentive_score: float | None = None
    windows_evaluated: int
    alpha_used: float
    updated_at: str


class BittensorRankingsResponse(BaseModel):
    rankings: list[MinerRankingItem]
    ranking_config: dict


# --- /api/bittensor/miners/{hotkey}/accuracy ---

class AccuracyRecordItem(BaseModel):
    window_id: str
    symbol: str
    timeframe: str
    direction_correct: bool
    predicted_return: float
    actual_return: float
    magnitude_error: float
    path_correlation: float | None = None
    outcome_bars: int
    scoring_version: str
    evaluated_at: str


class MinerAccuracyResponse(BaseModel):
    hotkey: str
    records: list[AccuracyRecordItem]


# --- /api/bittensor/signals ---

class BittensorSignalsResponse(BaseModel):
    signals: list[dict]
```

- [ ] **Step 2: Wire response models into route decorators**

In `trading/api/routes/bittensor.py`, add the import at the top (after existing imports):

```python
from api.routes.bittensor_schemas import (
    BittensorMetricsResponse,
    BittensorRankingsResponse,
    BittensorSignalsResponse,
    BittensorStatusResponse,
    MinerAccuracyResponse,
)
```

Then update each route decorator:

```python
# Line 13 — status
@router.get("/api/bittensor/status", response_model=BittensorStatusResponse, response_model_exclude_none=True)

# Line 113 — rankings
@router.get("/api/bittensor/rankings", response_model=BittensorRankingsResponse, response_model_exclude_none=True)

# Line 144 — miner accuracy
@router.get("/api/bittensor/miners/{hotkey}/accuracy", response_model=MinerAccuracyResponse, response_model_exclude_none=True)

# Line 176 — metrics
@router.get("/api/bittensor/metrics", response_model=BittensorMetricsResponse, response_model_exclude_none=True)

# Line 224 — signals
@router.get("/api/bittensor/signals", response_model=BittensorSignalsResponse, response_model_exclude_none=True)
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['api/routes/bittensor_schemas.py', 'api/routes/bittensor.py']]; print('OK')"` from the `trading/` directory.
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add trading/api/routes/bittensor_schemas.py trading/api/routes/bittensor.py
git commit -m "docs(bittensor): add Pydantic response models for OpenAPI/Swagger generation"
```

---

### Task 5: Bittensor Status Page (Frontend)

**Files:**
- Rewrite: `frontend/src/pages/BittensorNode.tsx`

- [ ] **Step 1: Rewrite BittensorNode.tsx with live API data**

Replace the entire contents of `frontend/src/pages/BittensorNode.tsx`:

```tsx
import { useState, useEffect, useCallback } from 'react';
import { GlassCard } from '../components/GlassCard';
import { api } from '../lib/api/client';

interface StatusData {
  enabled: boolean;
  healthy?: boolean;
  scheduler?: {
    running: boolean;
    last_window_collected: string | null;
    next_window: string;
    windows_collected_total: number;
  };
  evaluator?: {
    running: boolean;
    last_evaluation: string | null;
    unevaluated_windows: number;
    windows_evaluated_total: number;
  };
  miners?: {
    total_in_metagraph: number;
    responded_last_window: number;
    response_rate: number;
    top_miners: Array<{
      hotkey: string;
      hybrid_score: number;
      direction_accuracy: number;
      windows_evaluated: number;
    }>;
  };
}

interface MetricsData {
  enabled: boolean;
  scheduler?: {
    windows_collected: number;
    windows_failed: number;
    hash_verifications_passed: number;
    hash_verifications_failed: number;
    last_collection_duration_secs: number;
    avg_collection_duration_secs: number;
    last_miner_response_rate: number;
    consecutive_failures: number;
  };
  evaluator?: {
    windows_evaluated: number;
    windows_expired: number;
    windows_skipped: number;
    last_skip_reason: string | null;
    last_evaluation_duration_secs: number;
  };
  weight_setter?: {
    weight_sets_total: number;
    weight_sets_failed: number;
    last_weight_set_block: number | null;
  };
}

function StatCard({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-4 font-mono text-center transition-all ${
      warn
        ? 'border-rose-500/40 bg-rose-500/5 shadow-[0_0_10px_rgba(244,63,94,0.15)]'
        : 'border-slate-800 bg-slate-950/40'
    }`}>
      <div className={`text-2xl font-bold ${warn ? 'text-rose-400' : 'text-slate-200'}`}>{value}</div>
      <div className="text-xs text-slate-500 uppercase tracking-widest mt-1">{label}</div>
    </div>
  );
}

function RunningBadge({ running }: { running?: boolean }) {
  if (running === undefined) return null;
  return running ? (
    <div className="flex items-center gap-2">
      <span className="text-xs text-cyan-500 font-mono">LIVE</span>
      <div className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
    </div>
  ) : (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 font-mono">OFFLINE</span>
      <div className="h-2 w-2 rounded-full bg-slate-600" />
    </div>
  );
}

export default function BittensorNode() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, metricsRes] = await Promise.all([
        api.get('/bittensor/status').catch(() => ({ data: null })),
        api.get('/bittensor/metrics').catch(() => ({ data: null })),
      ]);
      if (statusRes.data) setStatus(statusRes.data);
      if (metricsRes.data) setMetrics(metricsRes.data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-slate-600 font-mono text-sm uppercase tracking-widest animate-pulse">
          Connecting to validator node...
        </div>
      </div>
    );
  }

  if (!status?.enabled) {
    return (
      <div className="space-y-6 animate-in fade-in duration-500">
        <header className="flex flex-col gap-2">
          <h1 className="text-3xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400">
            Bittensor Validator Node
          </h1>
        </header>
        <GlassCard variant="default">
          <p className="text-slate-400 font-mono text-sm">Bittensor integration is not enabled. Set STA_BITTENSOR_ENABLED=true to activate.</p>
        </GlassCard>
      </div>
    );
  }

  const hashTotal = (metrics?.scheduler?.hash_verifications_passed ?? 0) + (metrics?.scheduler?.hash_verifications_failed ?? 0);
  const hashPassRate = hashTotal > 0
    ? ((metrics?.scheduler?.hash_verifications_passed ?? 0) / hashTotal) * 100
    : 0;
  const avgDuration = metrics?.scheduler?.avg_collection_duration_secs ?? 0;
  const responseRate = (metrics?.scheduler?.last_miner_response_rate ?? 0) * 100;
  const consecutiveFailures = metrics?.scheduler?.consecutive_failures ?? 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400">
          Bittensor Validator Node
        </h1>
        <p className="text-slate-400 font-mono text-sm">
          Subnet 8 (Taoshi PTN) — {status?.healthy ? 'All systems operational' : 'Degraded'}
        </p>
      </header>

      {/* Row 1: Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <GlassCard variant="cyan" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-cyan-400 font-mono text-sm tracking-wider uppercase">Scheduler</h2>
            <RunningBadge running={status?.scheduler?.running} />
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-cyan-500/10 pb-2">
              <span className="text-slate-500">Windows Collected</span>
              <span className="text-cyan-300">{status?.scheduler?.windows_collected_total ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-cyan-500/10 pb-2">
              <span className="text-slate-500">Last Collection</span>
              <span className="text-cyan-300 text-xs">{status?.scheduler?.last_window_collected ?? 'Never'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Next Window</span>
              <span className="text-cyan-300 text-xs">{status?.scheduler?.next_window ?? '—'}</span>
            </div>
          </div>
        </GlassCard>

        <GlassCard variant="violet" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-violet-400 font-mono text-sm tracking-wider uppercase">Evaluator</h2>
            <RunningBadge running={status?.evaluator?.running} />
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-violet-500/10 pb-2">
              <span className="text-slate-500">Windows Evaluated</span>
              <span className="text-violet-300">{status?.evaluator?.windows_evaluated_total ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-violet-500/10 pb-2">
              <span className="text-slate-500">Unevaluated</span>
              <span className="text-violet-300">{status?.evaluator?.unevaluated_windows ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-violet-500/10 pb-2">
              <span className="text-slate-500">Skipped</span>
              <span className="text-violet-300">{metrics?.evaluator?.windows_skipped ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Last Eval</span>
              <span className="text-violet-300 text-xs">{status?.evaluator?.last_evaluation ?? 'Never'}</span>
            </div>
          </div>
        </GlassCard>

        <GlassCard variant="green" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-emerald-400 font-mono text-sm tracking-wider uppercase">Weight Setter</h2>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-emerald-500/10 pb-2">
              <span className="text-slate-500">Sets Total</span>
              <span className="text-emerald-300">{metrics?.weight_setter?.weight_sets_total ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-emerald-500/10 pb-2">
              <span className="text-slate-500">Sets Failed</span>
              <span className={`${(metrics?.weight_setter?.weight_sets_failed ?? 0) > 0 ? 'text-rose-400' : 'text-emerald-300'}`}>
                {metrics?.weight_setter?.weight_sets_failed ?? 0}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Last Block</span>
              <span className="text-emerald-300">{metrics?.weight_setter?.last_weight_set_block ?? '—'}</span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Row 2: Compact Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Hash Pass Rate"
          value={hashTotal > 0 ? `${hashPassRate.toFixed(1)}%` : '—'}
          warn={hashTotal > 0 && hashPassRate < 80}
        />
        <StatCard
          label="Avg Collection"
          value={avgDuration > 0 ? `${avgDuration.toFixed(1)}s` : '—'}
          warn={avgDuration > 120}
        />
        <StatCard
          label="Miner Response"
          value={responseRate > 0 ? `${responseRate.toFixed(1)}%` : '—'}
          warn={responseRate > 0 && responseRate < 50}
        />
        <StatCard
          label="Consecutive Fails"
          value={String(consecutiveFailures)}
          warn={consecutiveFailures > 0}
        />
      </div>

      {/* Row 3: Miner Rankings */}
      <GlassCard className="flex flex-col gap-4 bg-slate-950/60 border-white/5">
        <div className="flex items-center justify-between border-b border-white/5 pb-4">
          <h2 className="text-slate-300 font-mono text-sm tracking-wider uppercase">
            Top Miners ({status?.miners?.total_in_metagraph ?? 0} in metagraph)
          </h2>
          <span className="text-xs font-mono text-slate-500">
            {status?.miners?.responded_last_window ?? 0} responded last window
          </span>
        </div>
        {(status?.miners?.top_miners?.length ?? 0) > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-sm">
              <thead>
                <tr className="text-slate-500 text-xs uppercase tracking-widest border-b border-white/5">
                  <th className="text-left py-2 pr-4">Hotkey</th>
                  <th className="text-right py-2 px-4">Hybrid Score</th>
                  <th className="text-right py-2 px-4">Direction Acc</th>
                  <th className="text-right py-2 pl-4">Windows</th>
                </tr>
              </thead>
              <tbody>
                {status!.miners!.top_miners.map((m) => (
                  <tr key={m.hotkey} className="border-b border-white/5 hover:bg-white/[0.02] transition">
                    <td className="py-2 pr-4 text-cyan-300" title={m.hotkey}>
                      {m.hotkey.slice(0, 8)}...{m.hotkey.slice(-4)}
                    </td>
                    <td className="py-2 px-4 text-right text-slate-300">{m.hybrid_score.toFixed(4)}</td>
                    <td className="py-2 px-4 text-right text-slate-300">{(m.direction_accuracy * 100).toFixed(1)}%</td>
                    <td className="py-2 pl-4 text-right text-slate-400">{m.windows_evaluated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-slate-500 font-mono text-sm py-8 text-center">No miners ranked yet</p>
        )}
      </GlassCard>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to `BittensorNode.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BittensorNode.tsx
git commit -m "feat(frontend): wire BittensorNode page to live API status and metrics"
```

---

### Task 6: Final Integration Commit

- [ ] **Step 1: Verify all Python syntax**

Run from `trading/`:
```bash
python3 -c "
import ast
files = [
    'integrations/bittensor/models.py',
    'integrations/bittensor/evaluator.py',
    'api/routes/bittensor.py',
    'api/routes/bittensor_schemas.py',
]
for f in files:
    ast.parse(open(f).read())
    print(f'OK: {f}')
"
```
Expected: All OK

- [ ] **Step 2: Verify PHP syntax**

Run: `php -l api/app/Http/Controllers/Auth/MagicLinkController.php`
Expected: `No syntax errors detected`

- [ ] **Step 3: Push to remote**

Run: `git push`
Expected: All commits pushed to `origin/main`
