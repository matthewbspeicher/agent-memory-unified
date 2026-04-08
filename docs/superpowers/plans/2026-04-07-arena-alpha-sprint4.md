# Arena Alpha Sprint 4: Funding Rate Arb Agent + Competitor Profiles

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the funding rate arbitrage agent strategy and build competitor profile pages in the frontend.

**Architecture:** New `FundingRateArbAgent` extends `StructuredAgent`, uses `DerivativesDataSource` for funding rates. Frontend profile page extends `AgentProfile.tsx` with ELO chart, stats, achievements.

**Tech Stack:** Python 3.13, React 19, recharts (for ELO chart)

**Prereqs:** Sprint 1-3 complete (competition system, exchange client, derivatives source)

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 2.3 + Section 3.2

---

### Task 1: Funding Rate Arb Agent

**Files:**
- Create: `trading/agents/adapters/funding_arb.py`
- Create: `tests/unit/agents/test_funding_arb.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agents/test_funding_arb.py
from __future__ import annotations

import pytest
import statistics
from agents.adapters.funding_arb import FundingRateArbAdapter, FundingArbConfig
from data.sources.derivatives import FundingOISnapshot


class TestFundingCalculations:
    def test_net_funding_positive_rate(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        # 30% annualized, fees ~14.6% annualized
        net = adapter.calculate_net_funding(0.30, "BTCUSD")
        assert net > 0.0  # Profitable after fees

    def test_net_funding_low_rate_unprofitable(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(min_annualized_rate=0.20))
        net = adapter.calculate_net_funding(0.05, "BTCUSD")
        # Below minimum, but still calculates
        assert net < 0.20  # Below entry threshold

    def test_net_funding_negative_disabled(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(allow_negative_funding=False))
        net = adapter.calculate_net_funding(-0.30, "BTCUSD")
        assert net == 0.0

    def test_net_funding_negative_enabled(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(allow_negative_funding=True))
        net = adapter.calculate_net_funding(-0.30, "BTCUSD")
        assert net > 0.0  # abs(rate) - borrow - fees


class TestExchangeDivergence:
    def test_agreement_when_all_close(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        snapshots = [
            FundingOISnapshot("BTC", "binance", 0.001, 1.095, 1e9, 0),
            FundingOISnapshot("BTC", "bybit", 0.0011, 1.2045, 1e9, 0),
            FundingOISnapshot("BTC", "okx", 0.00105, 1.14975, 1e9, 0),
        ]
        assert adapter.check_exchange_agreement(snapshots) is True

    def test_disagreement_when_outlier(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        snapshots = [
            FundingOISnapshot("BTC", "binance", 0.001, 1.095, 1e9, 0),
            FundingOISnapshot("BTC", "bybit", 0.0001, 0.1095, 1e9, 0),  # 10x lower
        ]
        assert adapter.check_exchange_agreement(snapshots) is False

    def test_needs_minimum_exchanges(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        snapshots = [FundingOISnapshot("BTC", "binance", 0.001, 1.095, 1e9, 0)]
        assert adapter.check_exchange_agreement(snapshots) is False


class TestSpikeDetection:
    def test_normal_rate_no_spike(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(spike_threshold=1.0))
        assert adapter.is_spike(0.50) is False

    def test_extreme_rate_is_spike(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(spike_threshold=1.0))
        assert adapter.is_spike(1.50) is True

    def test_spike_reduces_size(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(spike_size_multiplier=0.5))
        assert adapter.size_multiplier(annualized=1.5) == 0.5
        assert adapter.size_multiplier(annualized=0.3) == 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd trading && python -m pytest tests/unit/agents/test_funding_arb.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# trading/agents/adapters/funding_arb.py
"""Funding rate arbitrage strategy — delta-neutral long spot / short perp."""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from data.sources.derivatives import FundingOISnapshot

logger = logging.getLogger(__name__)

# Annualized borrow rate estimates for shorting spot
BORROW_RATES = {
    "BTCUSD": 0.02 * 365,  # ~2% daily annualized
    "ETHUSD": 0.03 * 365,
}
DEFAULT_BORROW_RATE = 0.05 * 365
# Base fee per funding period (0.04%), annualized
BASE_FEE_ANNUALIZED = 0.0004 * 3 * 365


@dataclass
class FundingArbConfig:
    min_annualized_rate: float = 0.20
    exit_rate: float = 0.05
    spike_threshold: float = 1.0
    spike_size_multiplier: float = 0.5
    allow_negative_funding: bool = False
    min_exchange_agreement: float = 0.80
    agreement_threshold: float = 0.10


@dataclass
class FundingArbSignal:
    direction: str  # "long_spot_short_perp" | "short_spot_long_perp" | "close"
    expected_annualized: float
    size_multiplier: float
    flags: list[str] = field(default_factory=list)
    confidence: float = 0.5


class FundingRateArbAdapter:
    """Evaluates funding rate arbitrage opportunities."""

    def __init__(self, config: FundingArbConfig | None = None):
        self.config = config or FundingArbConfig()

    def calculate_net_funding(self, annualized_rate: float, symbol: str) -> float:
        """Net return after fees and borrow costs."""
        if annualized_rate > 0:
            return annualized_rate - BASE_FEE_ANNUALIZED

        if not self.config.allow_negative_funding:
            return 0.0

        borrow = BORROW_RATES.get(symbol, DEFAULT_BORROW_RATE)
        net = abs(annualized_rate) - borrow - BASE_FEE_ANNUALIZED
        return max(net, 0.0)

    def check_exchange_agreement(self, snapshots: list[FundingOISnapshot]) -> bool:
        """Check if exchanges agree on funding rate direction and magnitude."""
        if len(snapshots) < 2:
            return False

        rates = [s.annualized_rate for s in snapshots]
        median_rate = statistics.median(rates)
        if abs(median_rate) < 0.01:
            return False

        agreeing = sum(
            1 for r in rates
            if abs(r - median_rate) / max(abs(median_rate), 0.01) < self.config.agreement_threshold
        )
        return (agreeing / len(rates)) >= self.config.min_exchange_agreement

    def is_spike(self, annualized_rate: float) -> bool:
        return abs(annualized_rate) > self.config.spike_threshold

    def size_multiplier(self, annualized: float) -> float:
        if self.is_spike(annualized):
            return self.config.spike_size_multiplier
        return 1.0

    def evaluate(
        self,
        snapshots: list[FundingOISnapshot],
        symbol: str,
        has_position: bool = False,
    ) -> FundingArbSignal | None:
        """Evaluate funding snapshots and produce a signal."""
        if not self.check_exchange_agreement(snapshots):
            return None

        rates = [s.annualized_rate for s in snapshots]
        median_rate = statistics.median(rates)
        net = self.calculate_net_funding(median_rate, symbol)

        flags: list[str] = []
        if self.is_spike(median_rate):
            flags.append("spike_anomaly")

        # Entry signal
        if not has_position and net >= self.config.min_annualized_rate:
            direction = "long_spot_short_perp" if median_rate > 0 else "short_spot_long_perp"
            return FundingArbSignal(
                direction=direction,
                expected_annualized=net,
                size_multiplier=self.size_multiplier(median_rate),
                flags=flags,
                confidence=min(net / 0.5, 1.0),
            )

        # Exit signal
        if has_position and net < self.config.exit_rate:
            return FundingArbSignal(
                direction="close",
                expected_annualized=net,
                size_multiplier=1.0,
                flags=["exit_low_funding"],
                confidence=0.8,
            )

        return None
```

- [ ] **Step 4: Run tests**

Run: `cd trading && python -m pytest tests/unit/agents/test_funding_arb.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/agents/adapters/funding_arb.py tests/unit/agents/test_funding_arb.py
git commit -m "feat(agents): add FundingRateArbAdapter with delta-neutral strategy"
```

---

### Task 2: Frontend — EloChart + Sparkline Components

**Files:**
- Create: `frontend/src/components/charts/Sparkline.tsx`
- Create: `frontend/src/components/competition/EloChart.tsx`
- Create: `frontend/src/components/competition/CalibrationGauge.tsx`
- Create: `frontend/src/components/competition/MetaLearnerPanel.tsx`

- [ ] **Step 1: Write Sparkline**

```tsx
// frontend/src/components/charts/Sparkline.tsx
interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export function Sparkline({ data, width = 120, height = 30, color = '#00D4FF' }: SparklineProps) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={points} />
    </svg>
  );
}
```

- [ ] **Step 2: Write EloChart**

```tsx
// frontend/src/components/competition/EloChart.tsx
import { useEloHistory, type EloHistoryPoint } from '../../lib/api/competition';
import { Sparkline } from '../charts/Sparkline';

interface EloChartProps {
  competitorId: string;
  asset?: string;
  days?: number;
  compact?: boolean;
}

export function EloChart({ competitorId, asset = 'BTC', days = 30, compact = false }: EloChartProps) {
  const { data, isLoading } = useEloHistory(competitorId, asset, days);

  if (isLoading || !data?.history.length) {
    return <div className="h-8 bg-gray-800 rounded animate-pulse" />;
  }

  const elos = data.history.map((h: EloHistoryPoint) => h.elo);
  const current = elos[elos.length - 1];
  const start = elos[0];
  const delta = current - start;
  const deltaColor = delta >= 0 ? '#10B981' : '#EF4444';

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Sparkline data={elos} color={deltaColor} />
        <span style={{ color: deltaColor }} className="text-xs font-mono">
          {delta >= 0 ? '+' : ''}{delta}
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold font-mono">{current}</span>
        <span style={{ color: deltaColor }} className="text-sm font-mono">
          {delta >= 0 ? '+' : ''}{delta} ({days}d)
        </span>
      </div>
      <Sparkline data={elos} width={300} height={60} color={deltaColor} />
    </div>
  );
}
```

- [ ] **Step 3: Write CalibrationGauge**

```tsx
// frontend/src/components/competition/CalibrationGauge.tsx
interface CalibrationGaugeProps {
  score: number;
  sampleSize?: number;
}

export function CalibrationGauge({ score, sampleSize }: CalibrationGaugeProps) {
  const color = score >= 0.8 ? '#10B981' : score >= 0.6 ? '#F59E0B' : '#EF4444';
  const label = score >= 0.8 ? 'Calibrated' : score >= 0.6 ? 'Drifting' : 'Unreliable';

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-500">Calibration</span>
        <span style={{ color }}>{label} ({(score * 100).toFixed(0)}%{sampleSize ? `, n=${sampleSize}` : ''})</span>
      </div>
      <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score * 100}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write MetaLearnerPanel placeholder**

```tsx
// frontend/src/components/competition/MetaLearnerPanel.tsx
export function MetaLearnerPanel() {
  return (
    <div className="p-3 bg-gray-800/50 rounded border border-gray-700">
      <h3 className="text-sm font-semibold text-gray-400 mb-2">Meta-Learner</h3>
      <p className="text-xs text-gray-500">Coming in Sprint 7 — XGBoost meta-learner will show ensemble weights and feature importance here.</p>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/charts/Sparkline.tsx frontend/src/components/competition/EloChart.tsx frontend/src/components/competition/CalibrationGauge.tsx frontend/src/components/competition/MetaLearnerPanel.tsx
git commit -m "feat(frontend): add EloChart, Sparkline, CalibrationGauge components"
```

---

### Task 3: Extend AgentProfile as Competitor Profile

**Files:**
- Modify: `frontend/src/pages/AgentProfile.tsx`

- [ ] **Step 1: Read current AgentProfile.tsx**

Read `frontend/src/pages/AgentProfile.tsx` to understand its current structure.

- [ ] **Step 2: Add competition sections**

Add imports and competition panels to the profile page. After the existing agent info section, add:

```tsx
import { useCompetitor } from '../lib/api/competition';
import { EloChart } from '../components/competition/EloChart';
import { TierBadge } from '../components/competition/TierBadge';
import { CalibrationGauge } from '../components/competition/CalibrationGauge';
import { MetaLearnerPanel } from '../components/competition/MetaLearnerPanel';
```

Add a competition section that shows:
- TierBadge + current ELO
- EloChart (non-compact)
- Stats panel (matches, win rate, best streak)
- CalibrationGauge
- MetaLearnerPanel placeholder

Guard with `useCompetitor(id)` — if no competition data, skip the section gracefully.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AgentProfile.tsx
git commit -m "feat(frontend): extend AgentProfile with competition data"
```

- [ ] **Step 4: Final Sprint 4 commit**

```bash
git add -A
git commit -m "feat: complete Sprint 4 — funding arb agent and competitor profiles"
```
