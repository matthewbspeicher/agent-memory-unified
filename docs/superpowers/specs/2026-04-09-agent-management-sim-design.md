# Agent Management Sim — Gamification System

**Date:** 2026-04-09  
**Author:** Claude + mspeicher  
**Status:** Concept (ready for sprinting)

---

## Overview

Transform the Arena dashboard into a full-blown **quant agent management sim** — think Fantasy Football meets Crypto Trading Bot. Users don't just see leaderboards; they **collect, level up, and specialize** their agent fleet.

The existing Arena competition layer (ELO, tiers, achievements) becomes the **competitive backbone**. The gamification layer sits above it, adding RPG-style progression, visual collectibles, and daily challenges that make managing agents addictive.

---

## Core Systems

### 1. Agent XP & Leveling

Agents earn XP from competitive performance:

| XP Source | Amount | Trigger |
|----------|--------|---------|
| Match win (vs baseline) | +10 XP | Every correct directional call |
| Match win (vs competitor) | +25 XP | Pairwise match win |
| Streak milestone | +50 XP | Every 5 consecutive correct |
| Achievement earned (common) | +30 XP | Achievement unlock |
| Achievement earned (rare) | +75 XP | Achievement unlock |
| Achievement earned (legendary) | +200 XP | Achievement unlock |
| Tier promotion | +100 XP | Silver→Gold, Gold→Diamond |
| Sharpe > 2.0 (7d rolling) | +40 XP | Per achievement |
| Diamond maintenance (daily) | +5 XP | Hold Diamond for a day |

**Level Formula:** `level = floor(sqrt(xp / 100))`  
→ Lv. 1: 0 XP, Lv. 5: 500 XP, Lv. 10: 2,000 XP, Lv. 20: 10,000 XP

**Visual:** Agent cards show level badge + XP bar to next level.

---

### 2. Unlockable Trait System

Agents unlock **specialization traits** as they level up. Traits are permanent unlocks that define an agent's identity and can be combined.

#### Trait Tree

```
                        [Genesis Agent]
                              │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
    [Risk Manager]    [Trend Follower]  [Mean Reversion]
           │                 │                 │
    ┌──────┴──────┐    ┌─────┴─────┐    ┌─────┴─────┐
    ▼             ▼    ▼           ▼    ▼           ▼
[Scaled]    [Tail-Hedged] [Momentum] [Breakout] [Range-Bound] [Statistical]
                                                              │
                                                        ┌──────┴──────┐
                                                        ▼             ▼
                                                 [Cointegration]  [Kalman Filter]
```

#### Trait Definitions

| Trait | Unlock Level | Effect | Icon |
|-------|-------------|--------|------|
| `genesis` | 0 | Base agent type | 🧬 |
| `risk_manager` | 5 | Unlocks volatility-targeting position sizing | 🛡️ |
| `tail_hedged` | 10 | Can run with tail risk overlays | 📉 |
| `trend_follower` | 5 | Unlocks momentum strategies | 📈 |
| `momentum` | 10 | Momentum signal generation | 🚀 |
| `breakout` | 15 | Breakout detection | 💥 |
| `mean_reversion` | 5 | Unlocks mean-reversion strategies | ↩️ |
| `range_bound` | 10 | Range-bound detection | 📊 |
| `statistical` | 15 | Statistical arbitrage | 📐 |
| `cointegration` | 20 | Pairs trading / cointegration | 🔗 |
| `kalman_filter` | 25 | Dynamic hedge ratios | ⚙️ |

#### Trait Combinations

Agents can have up to 3 active traits (primary + secondary + tertiary). Trait combinations create emergent strategies:
- `trend_follower` + `momentum` + `breakout` = Pure momentum agent
- `mean_reversion` + `statistical` + `cointegration` = Pairs trading agent
- `risk_manager` + `tail_hedged` + `trend_follower` = Defensive trend agent

#### Backend Changes

```python
# trading/competition/models.py
class AgentTraits(str, Enum):
    GENESIS = "genesis"
    RISK_MANAGER = "risk_manager"
    TAIL_HEDGED = "tail_hedged"
    TREND_FOLLOWER = "trend_follower"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    RANGE_BOUND = "range_bound"
    STATISTICAL = "statistical"
    COINTEGRATION = "cointegration"
    KALMAN_FILTER = "kalman_filter"

TRAIT_REQUIREMENTS = {
    AgentTraits.RISK_MANAGER: 5,
    AgentTraits.TREND_FOLLOWER: 5,
    AgentTraits.MEAN_REVERSION: 5,
    AgentTraits.TAIL_HEDGED: 10,
    AgentTraits.MOMENTUM: 10,
    AgentTraits.RANGE_BOUND: 10,
    AgentTraits.BREAKOUT: 15,
    AgentTraits.STATISTICAL: 15,
    AgentTraits.COINTEGRATION: 20,
    AgentTraits.KALMAN_FILTER: 25,
}

@dataclass
class AgentProfile:
    xp: int = 0
    level: int = 1
    traits: list[AgentTraits] = field(default_factory=list)
    achievements_earned: list[str] = field(default_factory=list)
    current_streak: int = 0
    best_streak: int = 0
    total_matches: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
```

---

### 3. Agent Cards (Visual Collectibles)

Agent cards are the **visual heart** of the management sim. Every agent gets a unique card that levels up, shows traits, and displays achievements.

#### Card Anatomy

```
┌─────────────────────────────────────────┐
│  [RANK #3]           [TIER 💎 DIAMOND]  │
│                                         │
│  ╔═══════════════════════════════════╗   │
│  ║     🧠 RSI_SCANNER              ║   │
│  ║     Level 12                    ║   │
│  ╚═══════════════════════════════════╝   │
│                                         │
│  [████████░░░░░░] 58% to Lv.13        │
│                                         │
│  Traits:                               │
│  [📈] [📊] [💥]                        │
│  Trend  Range   Breakout               │
│  Follower Bound                         │
│                                         │
│  ─────────────────────────────────────  │
│                                         │
│  Achievements:                          │
│  🔥🔥🔥🔥🔥⚡                           │
│  (Hot Streak x5, First Blood)           │
│                                         │
│  Stats:                                │
│  ELO: 1456 | W: 89 | L: 34 | D: 12   │
│  Best Streak: 14                       │
└─────────────────────────────────────────┘
```

#### Card Rarity (Cosmetic)

Card **border glow** based on achievement count:

| Achievement Count | Rarity | Border |
|-------------------|--------|--------|
| 0-1 | Common | Gray |
| 2-3 | Uncommon | Blue |
| 4-5 | Rare | Purple |
| 6-7 | Epic | Orange |
| 8+ | Legendary | Gold animated |

---

### 4. Daily & Weekly Missions

Rotating challenges that reward engagement:

#### Daily Missions (reset at midnight UTC)

| Mission | XP Reward | Condition |
|---------|-----------|-----------|
| `warm_up` | 20 XP | Complete 3 matches |
| `streak_starter` | 30 XP | Achieve 3 correct in a row |
| `sharpe_hunter` | 40 XP | Achieve 1.5+ Sharpe in daily matches |
| `consistency_check` | 25 XP | Win 50%+ of today's matches |

#### Weekly Missions (reset Sunday UTC)

| Mission | XP Reward | Condition |
|---------|-----------|-----------|
| `weekly_grind` | 150 XP | Complete 50 matches |
| `streak_master` | 200 XP | Achieve 10+ correct in a row |
| `achievement_hunter` | 175 XP | Earn 3 achievements |
| `diamond_defender` | 250 XP | Maintain Diamond tier all week |
| `comeback_kid_weekly` | 300 XP | Recover from Bronze to Silver |

#### Mission System Backend

```python
# trading/competition/missions.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

@dataclass
class Mission:
    id: str
    type: Literal["daily", "weekly"]
    xp_reward: int
    description: str
    target_value: int
    current_value: int = 0
    
    @property
    def progress(self) -> float:
        return min(self.current_value / self.target_value, 1.0)
    
    @property
    def completed(self) -> bool:
        return self.current_value >= self.target_value

class MissionTracker:
    def __init__(self, competitor_id: str):
        self.competitor_id = competitor_id
        self._daily_missions: dict[str, Mission] = {}
        self._weekly_missions: dict[str, Mission] = {}
        self._last_daily_reset: datetime | None = None
        self._last_weekly_reset: datetime | None = None
    
    def check_and_update(self, match_result: MatchResult) -> list[Mission]:
        """Check all missions against match result, return newly completed."""
        self._reset_if_needed()
        completed = []
        for m in self._all_missions():
            if m.completed:
                continue
            # Update counters based on match result
            self._update_mission(m, match_result)
            if m.completed:
                completed.append(m)
        return completed
    
    def _all_missions(self) -> list[Mission]:
        return list(self._daily_missions.values()) + list(self._weekly_missions.values())
```

---

### 5. Seasonal Leagues

Quarterly seasons with **soft reset**:

| Season Duration | 90 days (quarterly) |
|-----------------|----------------------|
| Entry | Start at 1000 ELO (reset) |
| Rewards | Season-exclusive achievements + titles |
| Archive | Final rankings frozen, viewable forever |

#### Season-Exclusive Achievements

| Achievement | Trigger | Rarity |
|-------------|---------|--------|
| `season_N_champion` | #1 at season end | Legendary |
| `season_N_top_10` | Top 10 at season end | Epic |
| `season_N_diamond` | Reach Diamond in season | Rare |

**Frontend:** Season toggle in leaderboard (`S1 | S2 | All-time`).

---

### 6. Fleet Management Dashboard

New **`/fleet`** page — the "management sim" home:

```
┌─────────────────────────────────────────────────────────┐
│  YOUR FLEET                          [Season 1]  [All]│
│  12 Agents | 3 Diamond | 2 Gold | 5 Silver | 2 Bronze  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐           │
│  │ Agent 1│ │ Agent 2│ │ Agent 3│ │ Agent 4│           │
│  │ Lv.15  │ │ Lv.12  │ │ Lv.8   │ │ Lv.5   │           │
│  │ 💎     │ │ 💎     │ │ 🥇     │ │ 🥈     │           │
│  │ [card] │ │ [card] │ │ [card] │ │ [card] │           │
│  └────────┘ └────────┘ └────────┘ └────────┘           │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  TODAY'S MISSIONS                    [↻ Reset in 4h]   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ ✅ Warm Up (3/3 matches)              +20 XP     │   │
│  │ 🔄 Streak Starter (5/10 correct)      +30 XP     │   │
│  │ 🔄 Sharpe Hunter (0/3 days)           +40 XP     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  FLEET STATS                                          │
│  Total XP: 45,230 | Avg Level: 8.4 | Total Traits: 24 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: XP & Level System (Foundation)

**Backend:**
- Add `xp` and `level` fields to `CompetitorRecord`
- XP calculation engine in `competition/engine.py`
- XP earned on: match wins, streaks, achievements, tier changes
- API endpoint: `GET /api/competition/competitors/{id}/xp`

**Frontend:**
- Add XP bar and level badge to `LeaderboardTable` row
- Add XP display to `AgentProfile` page
- Level badge component: `AgentLevelBadge.tsx`

**Files:**
- `trading/competition/models.py` — add XP/level fields
- `trading/competition/engine.py` — add XP calculation
- `trading/api/routes/competition.py` — add `/competitors/{id}/xp` endpoint
- `frontend/src/components/competition/AgentLevelBadge.tsx` — new
- `frontend/src/components/competition/LeaderboardTable.tsx` — update

---

### Phase 2: Trait System

**Backend:**
- Add `traits` field to `CompetitorRecord`
- Trait unlock logic in `competition/engine.py`
- Level-gated trait unlocking
- API endpoint: `GET /api/competition/competitors/{id}/traits`

**Frontend:**
- Trait display on `AgentProfile` (trait icons with tooltips)
- Trait tree visualization: `TraitTree.tsx`
- New `TraitBadge.tsx` component

**Files:**
- `trading/competition/models.py` — add Trait enum + requirements
- `trading/competition/engine.py` — trait unlock logic
- `trading/api/routes/competition.py` — add traits endpoint
- `frontend/src/components/competition/TraitTree.tsx` — new
- `frontend/src/components/competition/TraitBadge.tsx` — new

---

### Phase 3: Agent Cards (Visual Collectibles)

**Frontend:**
- New `AgentCard.tsx` component with full card anatomy
- Fleet management page: `/fleet`
- Card grid layout with hover animations
- Card detail modal on click

**Files:**
- `frontend/src/components/competition/AgentCard.tsx` — new
- `frontend/src/pages/Fleet.tsx` — new fleet management page
- `frontend/src/lib/api/competition.ts` — add fleet endpoints
- `frontend/src/App.tsx` — add `/fleet` route

---

### Phase 4: Missions System

**Backend:**
- `competition/missions.py` — MissionTracker class
- Daily/weekly mission generation
- Mission completion tracking in DB
- API endpoints: `GET /api/competition/missions`, `POST /api/competition/missions/{id}/claim`

**Frontend:**
- Mission panel component: `MissionPanel.tsx`
- Progress bars for active missions
- Notification on mission completion

**Files:**
- `trading/competition/missions.py` — new
- `trading/competition/store.py` — add mission persistence
- `trading/api/routes/competition.py` — add mission endpoints
- `frontend/src/components/competition/MissionPanel.tsx` — new

---

### Phase 5: Seasonal Leagues

**Backend:**
- Season model with start/end dates
- Season competitor state (separate ELO per season)
- Season archive queries
- API endpoints: `GET /api/competition/seasons`, `GET /api/competition/seasons/{id}/leaderboard`

**Frontend:**
- Season toggle in `LeaderboardTable`
- Season archive page
- Season-exclusive achievements display

**Files:**
- `trading/competition/models.py` — Season model
- `trading/competition/store.py` — season persistence
- `trading/api/routes/competition.py` — season endpoints
- `frontend/src/components/competition/SeasonSelector.tsx` — new

---

### Phase 6: Fleet Stats & Polish

**Backend:**
- Fleet aggregation endpoints (total XP, avg level, trait distribution)
- Achievement feed filtered to user's fleet

**Frontend:**
- Fleet stats dashboard section
- Animated level-up celebrations
- Achievement unlock animations
- Card rarity glow effects

**Files:**
- `trading/api/routes/competition.py` — fleet aggregation
- `frontend/src/pages/Fleet.tsx` — add stats section
- `frontend/src/components/competition/LevelUpAnimation.tsx` — new

---

## Data Model Additions

### New Tables

```sql
-- Agent XP and progression
CREATE TABLE agent_progression (
    competitor_id UUID PRIMARY KEY REFERENCES competitors(id),
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    traits TEXT[] DEFAULT '{}',
    achievements_earned TEXT[] DEFAULT '{}',
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    total_matches INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Mission tracking
CREATE TABLE mission_progress (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID REFERENCES competitors(id),
    mission_id VARCHAR(50) NOT NULL,
    mission_type VARCHAR(10) NOT NULL, -- 'daily' or 'weekly'
    current_value INTEGER DEFAULT 0,
    target_value INTEGER NOT NULL,
    xp_reward INTEGER NOT NULL,
    completed_at TIMESTAMPTZ,
    reset_at TIMESTAMPTZ NOT NULL,
    UNIQUE(competitor_id, mission_id, reset_at)
);
CREATE INDEX idx_mission_progress_competitor ON mission_progress(competitor_id, reset_at DESC);

-- Seasons
CREATE TABLE seasons (
    id SERIAL PRIMARY KEY,
    name VARCHAR(20) NOT NULL, -- 'Season 1', 'Season 2'
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    is_current BOOLEAN DEFAULT FALSE
);

-- Season-specific ELO (archived at season end)
CREATE TABLE season_elo (
    id BIGSERIAL PRIMARY KEY,
    season_id INTEGER REFERENCES seasons(id),
    competitor_id UUID REFERENCES competitors(id),
    elo INTEGER DEFAULT 1000,
    rank INTEGER,
    UNIQUE(season_id, competitor_id)
);

-- Fleet (groups competitors by owner/user)
CREATE TABLE fleets (
    id SERIAL PRIMARY KEY,
    owner_id VARCHAR(100) NOT NULL, -- user identifier
    competitor_id UUID REFERENCES competitors(id),
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(owner_id, competitor_id)
);
```

---

## File Manifest

### Backend (trading/competition/)

| File | Change | Description |
|------|--------|-------------|
| `models.py` | Modify | Add `AgentProgression`, `Mission`, `Season` models + Trait enum |
| `engine.py` | Modify | XP calculation, trait unlock logic |
| `missions.py` | Create | MissionTracker class |
| `store.py` | Modify | Add progression, mission, season persistence |
| `achievements.py` | Modify | Award XP on achievement earn |
| `routes/` | Modify | Add `/xp`, `/traits`, `/missions`, `/seasons` endpoints |

### Backend (trading/api/routes/)

| File | Change | Description |
|------|--------|-------------|
| `competition.py` | Modify | Add xp, traits, missions, seasons endpoints |

### Frontend (frontend/src/)

| File | Change | Description |
|------|--------|-------------|
| `lib/api/competition.ts` | Modify | Add XP, traits, missions, seasons API clients |
| `components/competition/AgentLevelBadge.tsx` | Create | Level badge with XP bar |
| `components/competition/TraitBadge.tsx` | Create | Trait icon with tooltip |
| `components/competition/TraitTree.tsx` | Create | Visual trait tree |
| `components/competition/AgentCard.tsx` | Create | Full agent card component |
| `components/competition/MissionPanel.tsx` | Create | Daily/weekly missions UI |
| `components/competition/SeasonSelector.tsx` | Create | Season toggle |
| `components/competition/LevelUpAnimation.tsx` | Create | Celebration animation |
| `pages/Fleet.tsx` | Create | Fleet management page |
| `pages/Arena.tsx` | Modify | Add season toggle, fleet link |
| `pages/AgentProfile.tsx` | Modify | Add XP bar, trait tree, agent card |
| `App.tsx` | Modify | Add `/fleet` route |

---

## Testing Strategy

| Phase | Tests |
|-------|-------|
| Phase 1 | XP calculation unit tests, level formula verification, XP API tests |
| Phase 2 | Trait unlock edge cases (level boundary), trait combination validation |
| Phase 3 | Agent card rendering tests, fleet aggregation API tests |
| Phase 4 | Mission reset logic (timezone handling), completion edge cases |
| Phase 5 | Season archive queries, ELO archival on season end |
| Phase 6 | Animation performance, fleet stats accuracy |

---

## Success Metrics

- **DAU/MAU ratio** for fleet page vs leaderboard page
- **Mission completion rate** — are users engaging with daily challenges?
- **Average session length** on fleet page
- **Feature adoption** — % of competitors with traits unlocked
- **Retention** — Do users return to check level-ups?
