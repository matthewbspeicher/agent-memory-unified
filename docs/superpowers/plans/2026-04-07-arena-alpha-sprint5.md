# Arena Alpha Sprint 5: Achievements + LunarCrush

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build event-driven achievement system with SSE feed. Wire LunarCrush into SentimentProvider.

**Architecture:** `achievements.py` checks badge conditions after each matcher batch. SSE endpoint streams events to frontend. LunarCrush added as secondary source in existing SentimentProvider.

**Tech Stack:** Python 3.13, sse-starlette, React 19

**Prereqs:** Sprint 1-4 complete

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 1 (Achievements) + Section 2.4 + Section 3.4

---

### Task 1: Achievement System

**Files:**
- Create: `trading/competition/achievements.py`
- Create: `tests/unit/competition/test_achievements.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/competition/test_achievements.py
from __future__ import annotations

import pytest
from competition.achievements import (
    AchievementChecker,
    AchievementProgress,
    AchievementType,
    CompetitorState,
)


class TestAchievementChecker:
    def test_streak_5_not_met(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=4, sharpe_7d=0.5, tier="silver", diamond_days_30d=0)
        result = checker.check(AchievementType.STREAK_5, state)
        assert result.earned is False
        assert result.progress == pytest.approx(4 / 5)

    def test_streak_5_met(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=5, sharpe_7d=0.5, tier="silver", diamond_days_30d=0)
        result = checker.check(AchievementType.STREAK_5, state)
        assert result.earned is True

    def test_streak_10_met(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=10, sharpe_7d=0.5, tier="silver", diamond_days_30d=0)
        result = checker.check(AchievementType.STREAK_10, state)
        assert result.earned is True

    def test_sharp_shooter_not_enough_signals(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=0, sharpe_7d=3.0, tier="silver", diamond_days_30d=0, signal_count_7d=5)
        result = checker.check(AchievementType.SHARP_SHOOTER, state)
        assert result.earned is False  # Need 10+ signals

    def test_sharp_shooter_met(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=0, sharpe_7d=2.5, tier="gold", diamond_days_30d=0, signal_count_7d=15)
        result = checker.check(AchievementType.SHARP_SHOOTER, state)
        assert result.earned is True

    def test_iron_throne_progress(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=0, sharpe_7d=1.0, tier="diamond", diamond_days_30d=20)
        result = checker.check(AchievementType.IRON_THRONE, state)
        assert result.earned is False  # Need 30 days
        assert result.progress == pytest.approx(20 / 30)

    def test_iron_throne_met(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=0, sharpe_7d=1.0, tier="diamond", diamond_days_30d=30)
        result = checker.check(AchievementType.IRON_THRONE, state)
        assert result.earned is True

    def test_all_achievements_return_progress(self):
        checker = AchievementChecker()
        state = CompetitorState(current_streak=3, sharpe_7d=1.5, tier="gold", diamond_days_30d=10, signal_count_7d=20)
        for atype in AchievementType:
            result = checker.check(atype, state)
            assert 0.0 <= result.progress <= 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd trading && python -m pytest tests/unit/competition/test_achievements.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# trading/competition/achievements.py
"""Event-driven achievement system for competitors."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AchievementType(str, Enum):
    STREAK_5 = "streak_5"
    STREAK_10 = "streak_10"
    SHARP_SHOOTER = "sharp_shooter"
    IRON_THRONE = "iron_throne"
    COMEBACK_KID = "comeback_kid"
    REGIME_SURVIVOR = "regime_survivor"
    WHALE_WHISPERER = "whale_whisperer"
    FIRST_BLOOD = "first_blood"


@dataclass
class CompetitorState:
    current_streak: int = 0
    sharpe_7d: float = 0.0
    tier: str = "silver"
    diamond_days_30d: int = 0
    signal_count_7d: int = 0
    promoted_from_bronze_to_gold: bool = False
    survived_regime_change: bool = False
    whale_correct: bool = False
    was_first_signal: bool = False


@dataclass
class AchievementProgress:
    achievement_type: AchievementType
    earned: bool
    progress: float  # 0.0 to 1.0
    current_value: float = 0
    target_value: float = 1


class AchievementChecker:
    """Checks all achievement conditions against competitor state."""

    def check(self, atype: AchievementType, state: CompetitorState) -> AchievementProgress:
        """Check if an achievement is earned and calculate progress."""
        checkers = {
            AchievementType.STREAK_5: self._check_streak_5,
            AchievementType.STREAK_10: self._check_streak_10,
            AchievementType.SHARP_SHOOTER: self._check_sharp_shooter,
            AchievementType.IRON_THRONE: self._check_iron_throne,
            AchievementType.COMEBACK_KID: self._check_comeback_kid,
            AchievementType.REGIME_SURVIVOR: self._check_regime_survivor,
            AchievementType.WHALE_WHISPERER: self._check_whale_whisperer,
            AchievementType.FIRST_BLOOD: self._check_first_blood,
        }
        return checkers[atype](state)

    def check_all(self, state: CompetitorState) -> list[AchievementProgress]:
        return [self.check(atype, state) for atype in AchievementType]

    def _check_streak_5(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.STREAK_5,
            earned=state.current_streak >= 5,
            progress=min(state.current_streak / 5, 1.0),
            current_value=state.current_streak,
            target_value=5,
        )

    def _check_streak_10(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.STREAK_10,
            earned=state.current_streak >= 10,
            progress=min(state.current_streak / 10, 1.0),
            current_value=state.current_streak,
            target_value=10,
        )

    def _check_sharp_shooter(self, state: CompetitorState) -> AchievementProgress:
        earned = state.sharpe_7d >= 2.0 and state.signal_count_7d >= 10
        progress = min(state.sharpe_7d / 2.0, 1.0) if state.signal_count_7d >= 10 else 0.0
        return AchievementProgress(
            AchievementType.SHARP_SHOOTER,
            earned=earned,
            progress=progress,
            current_value=state.sharpe_7d,
            target_value=2.0,
        )

    def _check_iron_throne(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.IRON_THRONE,
            earned=state.diamond_days_30d >= 30,
            progress=min(state.diamond_days_30d / 30, 1.0),
            current_value=state.diamond_days_30d,
            target_value=30,
        )

    def _check_comeback_kid(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.COMEBACK_KID,
            earned=state.promoted_from_bronze_to_gold,
            progress=1.0 if state.promoted_from_bronze_to_gold else 0.0,
        )

    def _check_regime_survivor(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.REGIME_SURVIVOR,
            earned=state.survived_regime_change,
            progress=1.0 if state.survived_regime_change else 0.0,
        )

    def _check_whale_whisperer(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.WHALE_WHISPERER,
            earned=state.whale_correct,
            progress=1.0 if state.whale_correct else 0.0,
        )

    def _check_first_blood(self, state: CompetitorState) -> AchievementProgress:
        return AchievementProgress(
            AchievementType.FIRST_BLOOD,
            earned=state.was_first_signal,
            progress=1.0 if state.was_first_signal else 0.0,
        )
```

- [ ] **Step 4: Run tests**

Run: `cd trading && python -m pytest tests/unit/competition/test_achievements.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/achievements.py tests/unit/competition/test_achievements.py
git commit -m "feat(competition): add achievement system with all 8 badge types"
```

---

### Task 2: SSE Achievement Feed Endpoint

**Files:**
- Modify: `trading/api/routes/competition.py`

- [ ] **Step 1: Install sse-starlette**

Run: `cd trading && pip install sse-starlette`

Also add to `pyproject.toml` or `requirements.txt` if present.

- [ ] **Step 2: Add SSE endpoint and feed query**

In `trading/api/routes/competition.py`, add:

```python
import asyncio
from sse_starlette.sse import EventSourceResponse


@router.get("/achievements/feed")
async def get_achievement_feed(
    request: Request,
    _: str = Depends(verify_api_key),
    limit: int = Query(20, ge=1, le=100),
):
    """Recent achievements, promotions, and events."""
    store = _get_store(request)
    sql = """
        SELECT a.id, a.competitor_id, a.achievement_type, a.earned_at, a.metadata,
               c.name, c.type
        FROM achievements a
        JOIN competitors c ON c.id = a.competitor_id
        ORDER BY a.earned_at DESC
        LIMIT $1
    """
    async with store._db.execute(sql, [limit]) as cur:
        rows = await cur.fetchall()
    return [
        {
            "id": row["id"],
            "competitor_name": row["name"],
            "competitor_type": row["type"],
            "achievement_type": row["achievement_type"],
            "earned_at": str(row["earned_at"]),
            "metadata": row.get("metadata", {}),
        }
        for row in rows
    ]


@router.get("/achievements/feed/stream")
async def achievement_feed_stream(request: Request):
    """SSE stream for real-time achievement updates."""
    store = _get_store(request)

    async def event_generator():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            sql = """
                SELECT a.id, a.competitor_id, a.achievement_type, a.earned_at,
                       c.name, c.type
                FROM achievements a
                JOIN competitors c ON c.id = a.competitor_id
                WHERE a.id > $1
                ORDER BY a.earned_at ASC LIMIT 10
            """
            async with store._db.execute(sql, [last_id]) as cur:
                rows = await cur.fetchall()
            for row in rows:
                last_id = row["id"]
                yield {
                    "event": "achievement_earned",
                    "id": str(row["id"]),
                    "data": f'{{"competitor":"{row["name"]}","type":"{row["achievement_type"]}","earned_at":"{row["earned_at"]}"}}',
                }
            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())
```

- [ ] **Step 3: Commit**

```bash
git add trading/api/routes/competition.py
git commit -m "feat(competition): add SSE achievement feed endpoint"
```

---

### Task 3: Frontend Achievement Components + Feed

**Files:**
- Create: `frontend/src/components/competition/AchievementBadge.tsx`
- Create: `frontend/src/components/competition/AchievementFeed.tsx`
- Create: `frontend/src/hooks/useAchievementFeed.ts`

- [ ] **Step 1: Write AchievementBadge**

```tsx
// frontend/src/components/competition/AchievementBadge.tsx
const BADGE_CONFIG: Record<string, { icon: string; label: string; rarity: string }> = {
  streak_5:         { icon: '🔥', label: 'Hot Streak',      rarity: 'common' },
  streak_10:        { icon: '🔥', label: 'Blazing Streak',  rarity: 'rare' },
  sharp_shooter:    { icon: '🎯', label: 'Sharp Shooter',   rarity: 'rare' },
  iron_throne:      { icon: '💎', label: 'Iron Throne',     rarity: 'legendary' },
  comeback_kid:     { icon: '⬆️', label: 'Comeback Kid',    rarity: 'legendary' },
  regime_survivor:  { icon: '🐂', label: 'Regime Survivor', rarity: 'rare' },
  whale_whisperer:  { icon: '🐋', label: 'Whale Whisperer', rarity: 'rare' },
  first_blood:      { icon: '⚡', label: 'First Blood',     rarity: 'rare' },
};

const RARITY_COLORS: Record<string, string> = {
  common: 'border-gray-600',
  rare: 'border-blue-500',
  legendary: 'border-yellow-500',
};

interface AchievementBadgeProps {
  type: string;
  earnedAt?: string;
  progress?: number;
}

export function AchievementBadge({ type, earnedAt, progress }: AchievementBadgeProps) {
  const cfg = BADGE_CONFIG[type] || { icon: '🏆', label: type, rarity: 'common' };
  const earned = !!earnedAt;
  const borderColor = earned ? RARITY_COLORS[cfg.rarity] : 'border-gray-800';

  return (
    <div className={`inline-flex items-center gap-2 px-2 py-1 rounded border ${borderColor} ${earned ? '' : 'opacity-50'}`}
         title={earned ? `Earned ${earnedAt}` : `${((progress ?? 0) * 100).toFixed(0)}% progress`}>
      <span>{cfg.icon}</span>
      <span className="text-xs">{cfg.label}</span>
      {!earned && progress != null && (
        <div className="w-8 h-1 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full" style={{ width: `${progress * 100}%` }} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write useAchievementFeed hook**

```typescript
// frontend/src/hooks/useAchievementFeed.ts
import { useState, useEffect, useRef } from 'react';

interface AchievementEvent {
  competitor: string;
  type: string;
  earned_at: string;
}

export function useAchievementFeed() {
  const [events, setEvents] = useState<AchievementEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const apiKey = import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : '');
    const es = new EventSource(`/api/competition/achievements/feed/stream?api_key=${apiKey}`);
    esRef.current = es;

    es.onopen = () => setIsConnected(true);
    es.onerror = () => setIsConnected(false);

    es.addEventListener('achievement_earned', (e) => {
      try {
        const data: AchievementEvent = JSON.parse(e.data);
        setEvents((prev) => [data, ...prev].slice(0, 50));
      } catch { /* ignore parse errors */ }
    });

    return () => es.close();
  }, []);

  return { events, isConnected };
}
```

- [ ] **Step 3: Write AchievementFeed**

```tsx
// frontend/src/components/competition/AchievementFeed.tsx
import { useAchievementFeed } from '../../hooks/useAchievementFeed';
import { AchievementBadge } from './AchievementBadge';

export function AchievementFeed() {
  const { events, isConnected } = useAchievementFeed();

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-400">Recent Activity</h3>
        <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
              title={isConnected ? 'Connected' : 'Disconnected'} />
      </div>
      {events.length === 0 && (
        <p className="text-xs text-gray-600">No recent activity</p>
      )}
      {events.map((event, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <AchievementBadge type={event.type} earnedAt={event.earned_at} />
          <span className="text-gray-500">{event.competitor}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Add AchievementFeed to Arena.tsx sidebar**

In `frontend/src/pages/Arena.tsx`, add `<AchievementFeed />` in a sidebar column next to the leaderboard:

```tsx
import { AchievementFeed } from '../components/competition/AchievementFeed';

// In the JSX, wrap content in a grid:
<div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
  <div className="lg:col-span-3">
    {/* Existing leaderboard content */}
  </div>
  <div className="lg:col-span-1">
    <AchievementFeed />
  </div>
</div>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/competition/AchievementBadge.tsx frontend/src/components/competition/AchievementFeed.tsx frontend/src/hooks/useAchievementFeed.ts frontend/src/pages/Arena.tsx
git commit -m "feat(frontend): add achievement badges, SSE feed, and arena sidebar"
```

---

### Task 4: LunarCrush Integration

**Files:**
- Modify: `trading/intelligence/providers/sentiment.py`

- [ ] **Step 1: Read current SentimentProvider**

Read `trading/intelligence/providers/sentiment.py` to understand existing structure. It already has slots for LunarCrush (`galaxy_score`, `alt_rank`).

- [ ] **Step 2: Add LunarCrush fetch with MAD spike detection**

Add a `_fetch_lunarcrush` method that:
1. Checks `config.lunarcrush_enabled` and `config.lunarcrush_api_key`
2. Calls LunarCrush API: `GET https://lunarcrush.com/api4/public/coins/{symbol}/v1`
3. Extracts `galaxy_score`, `social_volume`, `social_dominance`
4. Applies MAD-based spike detection on social volume
5. Combines with existing Fear & Greed score

```python
import numpy as np

def _detect_social_spike(self, current: float, historical: list[float], threshold: float = 2.5) -> bool:
    if not historical or len(historical) < 5:
        return False
    arr = np.array(historical)
    median = np.median(arr)
    mad = np.median(np.abs(arr - median))
    if mad == 0:
        return False
    modified_z = 0.6745 * (current - median) / mad
    return modified_z > threshold
```

Galaxy Score thresholds for sentiment scoring:
```python
GALAXY_THRESHOLDS = {
    (0, 25): -0.8,    # very_bearish -> contrarian bullish
    (25, 40): -0.4,
    (40, 60): 0.0,
    (60, 75): 0.4,
    (75, 100): 0.8,   # very_bullish -> contrarian bearish (invert for contrarian)
}
```

- [ ] **Step 3: Run existing sentiment tests**

Run: `cd trading && python -m pytest tests/ -v --tb=short --timeout=30 -k sentiment`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add trading/intelligence/providers/sentiment.py
git commit -m "feat(intel): add LunarCrush social volume to SentimentProvider"
```

- [ ] **Step 5: Final Sprint 5 commit**

```bash
git add -A
git commit -m "feat: complete Sprint 5 — achievements, SSE feed, LunarCrush"
```
