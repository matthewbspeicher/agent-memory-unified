# Arena Alpha Sprint 7: XGBoost Meta-Learner + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build XGBoost walk-forward meta-learner with auto-fallback to linear baseline. Polish frontend with meta-learner panel, mobile responsive pass.

**Architecture:** `meta_learner.py` in competition module. `EnsembleRouter` wraps meta-learner + linear baseline with 7d-promote/3d-demote hysteresis. Feature importance surfaced on dashboard.

**Tech Stack:** Python 3.13, xgboost, scikit-learn, React 19

**Prereqs:** Sprint 1-6 complete

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 2.6 + Section 3.2 (Meta-Learner Panel)

---

### Task 1: XGBoost Meta-Learner

**Files:**
- Create: `trading/competition/meta_learner.py`
- Create: `tests/unit/competition/test_meta_learner.py`

- [ ] **Step 1: Install xgboost**

Run: `cd trading && pip install xgboost`

- [ ] **Step 2: Write failing tests**

```python
# tests/unit/competition/test_meta_learner.py
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone, timedelta
from competition.meta_learner import WalkForwardMetaLearner, EnsembleRouter


class TestWalkForwardMetaLearner:
    def test_should_retrain_initially(self):
        learner = WalkForwardMetaLearner()
        assert learner.should_retrain(datetime.now(timezone.utc)) is True

    def test_should_not_retrain_soon_after(self):
        learner = WalkForwardMetaLearner(retrain_frequency_hours=24)
        learner.last_retrain = datetime.now(timezone.utc)
        assert learner.should_retrain(datetime.now(timezone.utc)) is False

    def test_should_retrain_after_interval(self):
        learner = WalkForwardMetaLearner(retrain_frequency_hours=24)
        learner.last_retrain = datetime.now(timezone.utc) - timedelta(hours=25)
        assert learner.should_retrain(datetime.now(timezone.utc)) is True

    def test_softmax_weights_sum_to_one(self):
        learner = WalkForwardMetaLearner()
        predictions = {"a": 0.5, "b": 0.3, "c": -0.1}
        weights = learner._softmax_weights(predictions)
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.001)

    def test_softmax_higher_prediction_gets_more_weight(self):
        learner = WalkForwardMetaLearner()
        predictions = {"a": 0.5, "b": 0.1, "c": -0.2}
        weights = learner._softmax_weights(predictions)
        assert weights["a"] > weights["b"] > weights["c"]

    def test_fit_and_predict(self):
        learner = WalkForwardMetaLearner()
        # Synthetic training data
        np.random.seed(42)
        n = 100
        X = pd.DataFrame({
            "elo": np.random.randint(800, 1400, n),
            "confidence": np.random.uniform(0.3, 1.0, n),
            "streak": np.random.randint(-5, 10, n),
        })
        y = pd.Series(np.random.randn(n) * 0.01)  # Returns

        learner.fit(X, y)
        assert learner.model is not None

        # Predict weights
        sample = pd.DataFrame({"elo": [1200], "confidence": [0.8], "streak": [3]})
        pred = learner.predict(sample)
        assert len(pred) == 1


class TestEnsembleRouter:
    def test_starts_in_baseline_mode(self):
        router = EnsembleRouter(meta_learner=None, promote_days=7, demote_days=3)
        assert router.active_mode == "baseline"

    def test_promote_after_consecutive_wins(self):
        router = EnsembleRouter(meta_learner=None, promote_days=3, demote_days=2)
        for _ in range(3):
            router.record_daily_comparison(meta_won=True)
        assert router.active_mode == "meta"

    def test_demote_faster_than_promote(self):
        router = EnsembleRouter(meta_learner=None, promote_days=3, demote_days=2)
        # Promote first
        for _ in range(3):
            router.record_daily_comparison(meta_won=True)
        assert router.active_mode == "meta"
        # Demote
        for _ in range(2):
            router.record_daily_comparison(meta_won=False)
        assert router.active_mode == "baseline"

    def test_streak_resets_on_loss(self):
        router = EnsembleRouter(meta_learner=None, promote_days=3, demote_days=2)
        router.record_daily_comparison(meta_won=True)
        router.record_daily_comparison(meta_won=True)
        router.record_daily_comparison(meta_won=False)  # Resets
        router.record_daily_comparison(meta_won=True)
        assert router.active_mode == "baseline"  # Not promoted — streak broken
```

- [ ] **Step 3: Run to verify failure**

Run: `cd trading && python -m pytest tests/unit/competition/test_meta_learner.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# trading/competition/meta_learner.py
"""XGBoost walk-forward meta-learner with auto-fallback."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

XGB_CONFIG = {
    "max_depth": 4,
    "n_estimators": 100,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "verbosity": 0,
}


class WalkForwardMetaLearner:
    """XGBoost meta-learner with walk-forward validation."""

    def __init__(
        self,
        training_window_days: int = 30,
        gap_days: int = 1,
        retrain_frequency_hours: int = 24,
    ):
        self.training_window = timedelta(days=training_window_days)
        self.gap = timedelta(days=gap_days)
        self.retrain_freq = timedelta(hours=retrain_frequency_hours)
        self.model: Any = None
        self.feature_names: list[str] = []
        self.last_retrain: datetime | None = None
        self.feature_importance: dict[str, float] = {}

    def should_retrain(self, current_time: datetime) -> bool:
        if self.model is None or self.last_retrain is None:
            return True
        return (current_time - self.last_retrain) >= self.retrain_freq

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Train XGBoost model."""
        import xgboost as xgb

        self.feature_names = X.columns.tolist()

        # Train/val split (time-ordered, no shuffle)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        self.model = xgb.XGBRegressor(**XGB_CONFIG)
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        # Store feature importance
        importance = self.model.feature_importances_
        self.feature_importance = dict(zip(self.feature_names, importance.tolist()))

        self.last_retrain = datetime.now(timezone.utc)
        logger.info("meta_learner.trained", extra={
            "features": len(self.feature_names),
            "samples": len(X),
            "top_3": sorted(self.feature_importance, key=self.feature_importance.get, reverse=True)[:3],
        })

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict expected returns."""
        if self.model is None:
            return np.zeros(len(X))
        return self.model.predict(X)

    def predict_weights(self, competitor_features: dict[str, pd.DataFrame]) -> dict[str, float]:
        """Predict optimal weights for each competitor."""
        if self.model is None:
            n = len(competitor_features)
            return {cid: 1.0 / n for cid in competitor_features} if n else {}

        predictions = {}
        for comp_id, features in competitor_features.items():
            pred = self.predict(features)
            predictions[comp_id] = float(pred.mean()) if len(pred) else 0.0

        return self._softmax_weights(predictions)

    def _softmax_weights(self, predictions: dict[str, float]) -> dict[str, float]:
        """Softmax normalization of predictions to weights."""
        if not predictions:
            return {}
        values = np.array(list(predictions.values()))
        temperature = 0.5
        scaled = values / temperature
        exp_values = np.exp(scaled - np.max(scaled))
        weights = exp_values / exp_values.sum()
        return dict(zip(predictions.keys(), weights.tolist()))


class EnsembleRouter:
    """Routes between meta-learner and baseline with auto-fallback."""

    def __init__(
        self,
        meta_learner: WalkForwardMetaLearner | None,
        promote_days: int = 7,
        demote_days: int = 3,
    ):
        self.meta_learner = meta_learner
        self.promote_days = promote_days
        self.demote_days = demote_days
        self.active_mode: Literal["meta", "baseline"] = "baseline"
        self._meta_win_streak = 0
        self._baseline_win_streak = 0

    def record_daily_comparison(self, meta_won: bool) -> None:
        """Record whether meta-learner outperformed baseline today."""
        if meta_won:
            self._meta_win_streak += 1
            self._baseline_win_streak = 0
        else:
            self._baseline_win_streak += 1
            self._meta_win_streak = 0

        # Check promotion
        if self.active_mode == "baseline" and self._meta_win_streak >= self.promote_days:
            self.active_mode = "meta"
            self._meta_win_streak = 0
            logger.info("ensemble.switched mode=meta_learner")

        # Check demotion
        if self.active_mode == "meta" and self._baseline_win_streak >= self.demote_days:
            self.active_mode = "baseline"
            self._baseline_win_streak = 0
            logger.info("ensemble.switched mode=baseline")

    def get_weights(self, competitor_features: dict[str, pd.DataFrame] | None = None) -> dict[str, float] | None:
        """Get ensemble weights from active mode."""
        if self.active_mode == "meta" and self.meta_learner and competitor_features:
            return self.meta_learner.predict_weights(competitor_features)
        return None  # Caller falls back to linear baseline
```

- [ ] **Step 5: Run tests**

Run: `cd trading && python -m pytest tests/unit/competition/test_meta_learner.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add trading/competition/meta_learner.py tests/unit/competition/test_meta_learner.py
git commit -m "feat(competition): add XGBoost meta-learner with EnsembleRouter"
```

---

### Task 2: Meta-Learner API Endpoint

**Files:**
- Modify: `trading/api/routes/competition.py`

- [ ] **Step 1: Add endpoint**

```python
@router.get("/meta-learner/weights")
async def get_meta_learner_weights(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Current meta-learner weights and feature importance."""
    meta = getattr(request.app.state, "meta_learner", None)
    router_obj = getattr(request.app.state, "ensemble_router", None)

    return {
        "active_mode": router_obj.active_mode if router_obj else "baseline",
        "feature_importance": meta.feature_importance if meta else {},
        "last_retrain": str(meta.last_retrain) if meta and meta.last_retrain else None,
    }
```

- [ ] **Step 2: Commit**

```bash
git add trading/api/routes/competition.py
git commit -m "feat(competition): add meta-learner weights API endpoint"
```

---

### Task 3: Frontend Meta-Learner Panel + Polish

**Files:**
- Modify: `frontend/src/components/competition/MetaLearnerPanel.tsx`
- Modify: `frontend/src/lib/api/competition.ts`

- [ ] **Step 1: Add API hook**

In `competition.ts`:

```typescript
export interface MetaLearnerWeights {
  active_mode: 'meta' | 'baseline';
  feature_importance: Record<string, number>;
  last_retrain: string | null;
}

// Add to competitionApi:
getMetaLearnerWeights: () =>
  tradingApi.get<MetaLearnerWeights>('/competition/meta-learner/weights').then(res => res.data),

// Add hook:
export function useMetaLearnerWeights() {
  return useQuery({
    queryKey: ['competition', 'meta-learner'],
    queryFn: () => competitionApi.getMetaLearnerWeights(),
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 2: Update MetaLearnerPanel**

Replace the placeholder in `MetaLearnerPanel.tsx`:

```tsx
// frontend/src/components/competition/MetaLearnerPanel.tsx
import { useMetaLearnerWeights } from '../../lib/api/competition';

export function MetaLearnerPanel() {
  const { data, isLoading } = useMetaLearnerWeights();

  if (isLoading) return <div className="h-20 bg-gray-800 rounded animate-pulse" />;
  if (!data) return null;

  const topFeatures = Object.entries(data.feature_importance)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  const maxImportance = topFeatures[0]?.[1] || 1;

  return (
    <div className="p-3 bg-gray-800/50 rounded border border-gray-700 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-400">Meta-Learner</h3>
        <span className={`text-xs px-2 py-0.5 rounded ${
          data.active_mode === 'meta' ? 'bg-green-900/50 text-green-400' : 'bg-gray-700 text-gray-400'
        }`}>
          {data.active_mode === 'meta' ? 'XGBoost Active' : 'Linear Baseline'}
        </span>
      </div>

      {topFeatures.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500">Top Features</p>
          {topFeatures.map(([name, importance]) => (
            <div key={name} className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-24 truncate">{name}</span>
              <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full"
                  style={{ width: `${(importance / maxImportance) * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 w-8 text-right">
                {(importance * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}

      {data.last_retrain && (
        <p className="text-xs text-gray-600">
          Last retrain: {new Date(data.last_retrain).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/competition/MetaLearnerPanel.tsx frontend/src/lib/api/competition.ts
git commit -m "feat(frontend): add live MetaLearnerPanel with feature importance"
```

---

### Task 4: Final Integration + All Tests

- [ ] **Step 1: Run full competition test suite**

Run: `cd trading && python -m pytest tests/unit/competition/ -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 2: Run full unit test suite**

Run: `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30`
Expected: No regressions

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Sprint 7 — XGBoost meta-learner, ensemble router, full arena"
```
