# Arena Alpha Sprint 6: HMM Regime Detection + Head-to-Head

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace heuristic regime detection with 4-state HMM. Build head-to-head comparison page.

**Architecture:** Replace internals of `RegimeProvider.detect_regime()` with `hmmlearn.GaussianHMM`. Add `StableRegimeDetector` hysteresis wrapper. Frontend head-to-head page with signal timeline.

**Tech Stack:** Python 3.13, hmmlearn, joblib, scikit-learn, React 19

**Prereqs:** Sprint 1-5 complete

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 2.5 + Section 3.3

---

### Task 1: HMM Regime Provider

**Files:**
- Modify: `trading/intelligence/providers/regime.py`
- Create: `tests/unit/intelligence/test_hmm_regime.py`

- [ ] **Step 1: Install hmmlearn**

Run: `cd trading && pip install hmmlearn joblib`

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/intelligence/test_hmm_regime.py
from __future__ import annotations

import numpy as np
import pytest


class TestStableRegimeDetector:
    def test_initial_state_none(self):
        from intelligence.providers.regime import StableRegimeDetector
        detector = StableRegimeDetector(min_state_duration=3)
        assert detector.current_state is None

    def test_state_set_after_duration(self):
        from intelligence.providers.regime import StableRegimeDetector
        detector = StableRegimeDetector(min_state_duration=3)
        # First 3 updates with same state should set it
        for _ in range(3):
            state, changed = detector.update(0)
        assert detector.current_state == 0

    def test_no_flip_before_duration(self):
        from intelligence.providers.regime import StableRegimeDetector
        detector = StableRegimeDetector(min_state_duration=3)
        # Set initial state
        for _ in range(3):
            detector.update(0)
        # Try to flip — should resist
        state, changed = detector.update(1)
        assert state == 0
        assert changed is False

    def test_flip_after_sustained_change(self):
        from intelligence.providers.regime import StableRegimeDetector
        detector = StableRegimeDetector(min_state_duration=3)
        for _ in range(3):
            detector.update(0)
        # Sustain new state
        for _ in range(3):
            state, changed = detector.update(1)
        assert detector.current_state == 1
        assert changed is True


class TestRegimeStateMapping:
    def test_state_names(self):
        from intelligence.providers.regime import REGIME_STATES
        assert 0 in REGIME_STATES
        assert REGIME_STATES[0] == "trending_bull"
        assert REGIME_STATES[1] == "trending_bear"
        assert REGIME_STATES[2] == "volatile"
        assert REGIME_STATES[3] == "quiet"


class TestHMMFeatureExtraction:
    def test_extract_features_shape(self):
        from intelligence.providers.regime import extract_hmm_features
        import pandas as pd
        # Synthetic daily data
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "close": 50000 + np.cumsum(np.random.randn(100) * 500),
            "volume": np.random.uniform(1e9, 5e9, 100),
        }, index=dates)
        df["funding_rate"] = 0.001

        features = extract_hmm_features(df)
        assert features.shape[1] == 4  # log_return, vol_20d, volume_zscore, funding_rate
        assert features.shape[0] < 100  # Some rows dropped for rolling windows
        assert not np.isnan(features).any()
```

- [ ] **Step 3: Run to verify failure**

Run: `cd trading && python -m pytest tests/unit/intelligence/test_hmm_regime.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 4: Add HMM components to regime.py**

Read `trading/intelligence/providers/regime.py` first, then add the following at the module level:

```python
import numpy as np
import pandas as pd
import joblib
from pathlib import Path

REGIME_STATES = {
    0: "trending_bull",
    1: "trending_bear",
    2: "volatile",
    3: "quiet",
}


def extract_hmm_features(df: pd.DataFrame) -> np.ndarray:
    """Extract feature matrix for HMM from OHLCV data."""
    data = df.copy()
    data["log_return"] = np.log(data["close"] / data["close"].shift(1))
    data["realized_vol_20d"] = data["log_return"].rolling(20).std() * np.sqrt(365)
    vol_mean = data["volume"].rolling(20).mean()
    vol_std = data["volume"].rolling(20).std()
    data["volume_zscore"] = (data["volume"] - vol_mean) / vol_std.replace(0, 1)
    if "funding_rate" not in data.columns:
        data["funding_rate"] = 0.0
    else:
        data["funding_rate"] = data["funding_rate"].fillna(0)

    feature_cols = ["log_return", "realized_vol_20d", "volume_zscore", "funding_rate"]
    return data[feature_cols].dropna().values


class StableRegimeDetector:
    """Hysteresis wrapper — requires sustained state change before transition."""

    def __init__(self, min_state_duration: int = 3):
        self.min_state_duration = min_state_duration
        self.current_state: int | None = None
        self.state_age: int = 0
        self.pending_state: int | None = None
        self.pending_age: int = 0

    def update(self, raw_state: int) -> tuple[int | None, bool]:
        if self.current_state is None:
            if self.pending_state == raw_state:
                self.pending_age += 1
            else:
                self.pending_state = raw_state
                self.pending_age = 1
            if self.pending_age >= self.min_state_duration:
                self.current_state = raw_state
                self.state_age = self.pending_age
                self.pending_state = None
                self.pending_age = 0
                return self.current_state, False
            return None, False

        if raw_state == self.current_state:
            self.state_age += 1
            self.pending_state = None
            self.pending_age = 0
            return self.current_state, False

        if raw_state == self.pending_state:
            self.pending_age += 1
        else:
            self.pending_state = raw_state
            self.pending_age = 1

        if self.pending_age >= self.min_state_duration:
            self.current_state = self.pending_state
            self.state_age = self.pending_age
            self.pending_state = None
            self.pending_age = 0
            return self.current_state, True

        return self.current_state, False
```

Then modify the existing `RegimeProvider.analyze()` method to use HMM when `config.hmm_regime_enabled` is True, falling back to the existing heuristic otherwise. The HMM model file lives at `models/regime_hmm.pkl`.

- [ ] **Step 5: Run tests**

Run: `cd trading && python -m pytest tests/unit/intelligence/test_hmm_regime.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add trading/intelligence/providers/regime.py tests/unit/intelligence/test_hmm_regime.py
git commit -m "feat(intel): add HMM regime detection with StableRegimeDetector"
```

---

### Task 2: Head-to-Head API Endpoint

**Files:**
- Modify: `trading/api/routes/competition.py`
- Modify: `trading/api/routes/competition_schemas.py`
- Modify: `trading/competition/store.py`

- [ ] **Step 1: Add head-to-head store method**

In `trading/competition/store.py`, add:

```python
    async def get_head_to_head(
        self, competitor_a: str, competitor_b: str, asset: str = "BTC"
    ) -> dict:
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE winner_id = $1) AS wins_a,
                COUNT(*) FILTER (WHERE winner_id = $2) AS wins_b,
                COUNT(*) FILTER (WHERE winner_id IS NULL) AS draws,
                COUNT(*) AS total
            FROM matches
            WHERE ((competitor_a_id = $1 AND competitor_b_id = $2)
                OR (competitor_a_id = $2 AND competitor_b_id = $1))
                AND asset = $3
                AND match_type = 'pairwise'
        """
        async with self._db.execute(sql, [competitor_a, competitor_b, asset]) as cur:
            row = await cur.fetchone()
        return row or {"wins_a": 0, "wins_b": 0, "draws": 0, "total": 0}
```

- [ ] **Step 2: Add schema and route**

In `competition_schemas.py`:
```python
class HeadToHeadResponse(BaseModel):
    competitor_a: CompetitorResponse
    competitor_b: CompetitorResponse
    wins_a: int
    wins_b: int
    draws: int
    total_matches: int
```

In `competition.py`:
```python
@router.get("/head-to-head/{competitor_a}/{competitor_b}")
async def head_to_head(
    competitor_a: str,
    competitor_b: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    store = _get_store(request)
    stats = await store.get_head_to_head(competitor_a, competitor_b, asset)
    rec_a = await store.get_competitor(competitor_a)
    rec_b = await store.get_competitor(competitor_b)
    if not rec_a or not rec_b:
        from fastapi import HTTPException
        raise HTTPException(404, "Competitor not found")
    # Build response using LeaderboardEntry for competitor summaries
    return {
        "wins_a": stats.get("wins_a", 0),
        "wins_b": stats.get("wins_b", 0),
        "draws": stats.get("draws", 0),
        "total_matches": stats.get("total", 0),
        "competitor_a": rec_a,
        "competitor_b": rec_b,
    }
```

- [ ] **Step 3: Commit**

```bash
git add trading/api/routes/competition.py trading/api/routes/competition_schemas.py trading/competition/store.py
git commit -m "feat(competition): add head-to-head API endpoint"
```

---

### Task 3: Frontend Head-to-Head Page

**Files:**
- Modify: `frontend/src/pages/ArenaMatch.tsx`
- Create: `frontend/src/components/competition/RegimeIndicator.tsx`
- Modify: `frontend/src/lib/api/competition.ts`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Add API hooks**

In `frontend/src/lib/api/competition.ts`, add:

```typescript
export interface HeadToHeadResponse {
  competitor_a: Competitor;
  competitor_b: Competitor;
  wins_a: number;
  wins_b: number;
  draws: number;
  total_matches: number;
}

// Add to competitionApi:
getHeadToHead: (a: string, b: string, asset = 'BTC') =>
  tradingApi.get<HeadToHeadResponse>(`/competition/head-to-head/${a}/${b}`, { params: { asset } })
    .then(res => res.data),

// Add hook:
export function useHeadToHead(a: string, b: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'h2h', a, b, asset],
    queryFn: () => competitionApi.getHeadToHead(a, b, asset),
    enabled: !!a && !!b,
  });
}
```

- [ ] **Step 2: Write RegimeIndicator**

```tsx
// frontend/src/components/competition/RegimeIndicator.tsx
const REGIME_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  trending_bull:  { label: 'Bull',     color: '#10B981', bg: 'rgba(16, 185, 129, 0.15)' },
  trending_bear:  { label: 'Bear',     color: '#EF4444', bg: 'rgba(239, 68, 68, 0.15)' },
  volatile:       { label: 'Volatile', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.15)' },
  quiet:          { label: 'Quiet',    color: '#6B7280', bg: 'rgba(107, 114, 128, 0.15)' },
};

export function RegimeIndicator({ regime }: { regime: string }) {
  const cfg = REGIME_CONFIG[regime] || REGIME_CONFIG.quiet;
  return (
    <span
      style={{ color: cfg.color, backgroundColor: cfg.bg }}
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
    >
      {cfg.label}
    </span>
  );
}
```

- [ ] **Step 3: Rewrite ArenaMatch.tsx for head-to-head**

Read `frontend/src/pages/ArenaMatch.tsx` first, then rewrite to show:
- Two competitor cards side by side with `TierBadge` and ELO
- Win/loss/draw record as a bar chart
- `EloChart` for each competitor (compact sparkline)

Route: `/arena/match/:a/:b` (update router.tsx to match two params).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ArenaMatch.tsx frontend/src/components/competition/RegimeIndicator.tsx frontend/src/lib/api/competition.ts frontend/src/router.tsx
git commit -m "feat(frontend): add head-to-head page and regime indicator"
```

- [ ] **Step 5: Final Sprint 6 commit**

```bash
git add -A
git commit -m "feat: complete Sprint 6 — HMM regime detection and head-to-head"
```
