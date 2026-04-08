# Arena Alpha Sprint 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up competition tables, models, ELO engine, auto-registration, leaderboard API, and basic frontend.

**Architecture:** New `trading/competition/` module with store (raw SQL), engine (pure functions), registry (startup scan). API routes at `/api/competition/*`. Frontend leaderboard on `/arena`.

**Tech Stack:** Python 3.13, asyncpg, Pydantic, FastAPI, React 19, TanStack Query

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md` — Section 1 + Section 3.1 + Section 4 Sprint 1

---

### Task 1: Database Schema

**Files:**
- Create: `scripts/competition-tables.sql`

- [ ] **Step 1: Write the SQL DDL**

```sql
-- scripts/competition-tables.sql
-- Competition system tables for Arena Alpha

CREATE TABLE IF NOT EXISTS competitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL CHECK (type IN ('agent', 'miner', 'provider')),
    name VARCHAR(100) NOT NULL,
    ref_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'shadow', 'retired')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(type, ref_id)
);

CREATE TABLE IF NOT EXISTS elo_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    elo INTEGER DEFAULT 1000,
    tier VARCHAR(20) DEFAULT 'silver' CHECK (tier IN ('bronze', 'silver', 'gold', 'diamond')),
    matches_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset)
);

CREATE TABLE IF NOT EXISTS elo_history (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    elo INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL,
    elo_delta INTEGER DEFAULT 0,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_elo_history_lookup
    ON elo_history(competitor_id, asset, recorded_at DESC);

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    competitor_a_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    competitor_b_id UUID REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    window VARCHAR(10) NOT NULL,
    winner_id UUID,
    score_a DECIMAL(10, 6),
    score_b DECIMAL(10, 6),
    elo_delta_a INTEGER,
    elo_delta_b INTEGER,
    match_type VARCHAR(20) CHECK (match_type IN ('baseline', 'pairwise')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_matches_lookup
    ON matches(competitor_a_id, competitor_b_id, created_at DESC);

CREATE TABLE IF NOT EXISTS achievements (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    achievement_type VARCHAR(50) NOT NULL,
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_achievements_lookup
    ON achievements(competitor_id, achievement_type);

CREATE TABLE IF NOT EXISTS streaks (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    streak_type VARCHAR(30) NOT NULL,
    current_count INTEGER DEFAULT 0,
    best_count INTEGER DEFAULT 0,
    last_event_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset, streak_type)
);

CREATE TABLE IF NOT EXISTS competition_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    matches_created INTEGER DEFAULT 0,
    achievements_awarded INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);
```

- [ ] **Step 2: Verify DDL syntax**

Run: `cd /opt/agent-memory-unified && python -c "print('SQL file exists:', __import__('pathlib').Path('scripts/competition-tables.sql').exists())"`
Expected: `SQL file exists: True`

- [ ] **Step 3: Commit**

```bash
git add scripts/competition-tables.sql
git commit -m "feat(competition): add DDL for competition tables"
```

---

### Task 2: Competition Config

**Files:**
- Modify: `trading/config.py`

- [ ] **Step 1: Add CompetitionConfig to config.py**

Add after the `LLMConfig` class (around line 77):

```python
class CompetitionConfig(BaseModel):
    """Arena competition system configuration."""
    enabled: bool = True
    initial_elo: int = 1000
    elo_decay_enabled: bool = True
    funding_arb_enabled: bool = False
    hmm_regime_enabled: bool = False
    meta_learner_enabled: bool = False
    lunarcrush_enabled: bool = False
```

- [ ] **Step 2: Register in Config class**

Add to the `Config` class fields (after `intel`):

```python
    competition: CompetitionConfig = Field(default_factory=CompetitionConfig)
```

Add `"competition"` to `_NESTED_PREFIXES`:

```python
    _NESTED_PREFIXES = {"broker": "broker", "bittensor": "bittensor", "llm": "llm", "intel": "intel", "competition": "competition"}
```

- [ ] **Step 3: Verify config loads**

Run: `cd trading && python -c "from config import load_config; c = load_config(); print('competition_enabled:', c.competition.enabled)"`
Expected: `competition_enabled: True`

- [ ] **Step 4: Commit**

```bash
git add trading/config.py
git commit -m "feat(competition): add CompetitionConfig to config"
```

---

### Task 3: Pydantic Models

**Files:**
- Create: `trading/competition/__init__.py`
- Create: `trading/competition/models.py`
- Create: `tests/unit/competition/__init__.py`
- Create: `tests/unit/competition/test_models.py`

- [ ] **Step 1: Create module init**

```python
# trading/competition/__init__.py
```

```python
# tests/unit/competition/__init__.py
```

- [ ] **Step 2: Write model tests**

```python
# tests/unit/competition/test_models.py
from __future__ import annotations

import pytest
from competition.models import (
    CompetitorCreate,
    CompetitorRecord,
    CompetitorType,
    EloRating,
    LeaderboardEntry,
    Tier,
    tier_for_elo,
)


class TestTierForElo:
    def test_diamond(self):
        assert tier_for_elo(1400) == Tier.DIAMOND
        assert tier_for_elo(1500) == Tier.DIAMOND

    def test_gold(self):
        assert tier_for_elo(1200) == Tier.GOLD
        assert tier_for_elo(1399) == Tier.GOLD

    def test_silver(self):
        assert tier_for_elo(1000) == Tier.SILVER
        assert tier_for_elo(1199) == Tier.SILVER

    def test_bronze(self):
        assert tier_for_elo(999) == Tier.BRONZE
        assert tier_for_elo(0) == Tier.BRONZE


class TestCompetitorCreate:
    def test_valid_agent(self):
        c = CompetitorCreate(type=CompetitorType.AGENT, name="rsi_scanner", ref_id="rsi_scanner")
        assert c.type == CompetitorType.AGENT
        assert c.name == "rsi_scanner"

    def test_valid_miner(self):
        c = CompetitorCreate(
            type=CompetitorType.MINER,
            name="miner_5DkVM...",
            ref_id="5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha",
            metadata={"uid": 144},
        )
        assert c.metadata == {"uid": 144}

    def test_valid_provider(self):
        c = CompetitorCreate(type=CompetitorType.PROVIDER, name="sentiment", ref_id="sentiment")
        assert c.type == CompetitorType.PROVIDER


class TestLeaderboardEntry:
    def test_from_row(self):
        row = {
            "id": "abc-123",
            "type": "agent",
            "name": "rsi_scanner",
            "ref_id": "rsi_scanner",
            "status": "active",
            "elo": 1250,
            "tier": "gold",
            "matches_count": 42,
            "current_streak": 5,
            "best_streak": 8,
        }
        entry = LeaderboardEntry.from_row(row)
        assert entry.elo == 1250
        assert entry.tier == Tier.GOLD
        assert entry.streak == 5
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd trading && python -m pytest tests/unit/competition/test_models.py -v --tb=short --timeout=30`
Expected: FAIL — `ModuleNotFoundError: No module named 'competition.models'`

- [ ] **Step 4: Write models**

```python
# trading/competition/models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CompetitorType(str, Enum):
    AGENT = "agent"
    MINER = "miner"
    PROVIDER = "provider"


class Tier(str, Enum):
    DIAMOND = "diamond"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


def tier_for_elo(elo: int) -> Tier:
    if elo >= 1400:
        return Tier.DIAMOND
    if elo >= 1200:
        return Tier.GOLD
    if elo >= 1000:
        return Tier.SILVER
    return Tier.BRONZE


class CompetitorCreate(BaseModel):
    type: CompetitorType
    name: str
    ref_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompetitorRecord(BaseModel):
    id: str
    type: CompetitorType
    name: str
    ref_id: str
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EloRating(BaseModel):
    competitor_id: str
    asset: str
    elo: int = 1000
    tier: Tier = Tier.SILVER
    matches_count: int = 0


class LeaderboardEntry(BaseModel):
    id: str
    type: CompetitorType
    name: str
    ref_id: str
    status: str
    elo: int
    tier: Tier
    matches_count: int
    streak: int = 0
    best_streak: int = 0

    @classmethod
    def from_row(cls, row: dict) -> LeaderboardEntry:
        return cls(
            id=str(row["id"]),
            type=CompetitorType(row["type"]),
            name=row["name"],
            ref_id=row["ref_id"],
            status=row["status"],
            elo=row["elo"],
            tier=Tier(row["tier"]),
            matches_count=row["matches_count"],
            streak=row.get("current_streak", 0) or 0,
            best_streak=row.get("best_streak", 0) or 0,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd trading && python -m pytest tests/unit/competition/test_models.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add trading/competition/__init__.py trading/competition/models.py tests/unit/competition/__init__.py tests/unit/competition/test_models.py
git commit -m "feat(competition): add Pydantic models and tier logic"
```

---

### Task 4: ELO Engine (Pure Functions)

**Files:**
- Create: `trading/competition/engine.py`
- Create: `tests/unit/competition/test_engine.py`

- [ ] **Step 1: Write engine tests**

```python
# tests/unit/competition/test_engine.py
from __future__ import annotations

import pytest
from competition.engine import calculate_elo_delta, expected_score


class TestExpectedScore:
    def test_equal_ratings(self):
        assert expected_score(1000, 1000) == pytest.approx(0.5)

    def test_higher_rated_favored(self):
        score = expected_score(1400, 1000)
        assert score > 0.9

    def test_lower_rated_underdog(self):
        score = expected_score(1000, 1400)
        assert score < 0.1

    def test_symmetry(self):
        a = expected_score(1200, 1000)
        b = expected_score(1000, 1200)
        assert a + b == pytest.approx(1.0)


class TestCalculateEloDelta:
    def test_win_equal_ratings(self):
        delta = calculate_elo_delta(rating=1000, opponent_rating=1000, outcome=1.0, k=20)
        assert delta == 10  # K * (1 - 0.5) = 10

    def test_loss_equal_ratings(self):
        delta = calculate_elo_delta(rating=1000, opponent_rating=1000, outcome=0.0, k=20)
        assert delta == -10

    def test_draw_equal_ratings(self):
        delta = calculate_elo_delta(rating=1000, opponent_rating=1000, outcome=0.5, k=20)
        assert delta == 0

    def test_upset_win_big_delta(self):
        # Low-rated beats high-rated: big gain
        delta = calculate_elo_delta(rating=800, opponent_rating=1200, outcome=1.0, k=20)
        assert delta > 15

    def test_expected_win_small_delta(self):
        # High-rated beats low-rated: small gain
        delta = calculate_elo_delta(rating=1200, opponent_rating=800, outcome=1.0, k=20)
        assert delta < 5

    def test_custom_k_factor(self):
        delta_low = calculate_elo_delta(1000, 1000, 1.0, k=10)
        delta_high = calculate_elo_delta(1000, 1000, 1.0, k=40)
        assert delta_high == delta_low * 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd trading && python -m pytest tests/unit/competition/test_engine.py -v --tb=short --timeout=30`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write engine**

```python
# trading/competition/engine.py
"""ELO rating engine — pure functions, no side effects."""
from __future__ import annotations

import math


def expected_score(rating: int, opponent_rating: int) -> float:
    """ELO expected score: probability of winning."""
    return 1.0 / (1.0 + math.pow(10, (opponent_rating - rating) / 400.0))


def calculate_elo_delta(
    rating: int,
    opponent_rating: int,
    outcome: float,
    k: int = 20,
) -> int:
    """Calculate ELO rating change.

    Args:
        rating: Current player's rating.
        opponent_rating: Opponent's rating.
        outcome: 1.0 = win, 0.5 = draw, 0.0 = loss.
        k: K-factor (higher = more volatile).

    Returns:
        Integer ELO delta (positive = gained, negative = lost).
    """
    expected = expected_score(rating, opponent_rating)
    return round(k * (outcome - expected))


def k_factor_for_confidence(confidence: float, base_k: int = 20) -> int:
    """Adjust K-factor based on signal confidence."""
    if confidence >= 0.8:
        return round(base_k * 2.0)  # 40
    if confidence >= 0.5:
        return base_k  # 20
    return round(base_k * 0.5)  # 10


def k_factor_for_new_competitor(matches_count: int, base_k: int = 20) -> int:
    """New competitors get K*2 for first 10 matches."""
    if matches_count < 10:
        return base_k * 2
    return base_k
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd trading && python -m pytest tests/unit/competition/test_engine.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/engine.py tests/unit/competition/test_engine.py
git commit -m "feat(competition): add ELO engine with pure functions"
```

---

### Task 5: Competition Store (DB Access)

**Files:**
- Create: `trading/competition/store.py`
- Create: `tests/unit/competition/test_store.py`

- [ ] **Step 1: Write store tests with in-memory mock**

```python
# tests/unit/competition/test_store.py
from __future__ import annotations

import pytest
import pytest_asyncio
from competition.models import CompetitorCreate, CompetitorType, Tier
from competition.store import CompetitionStore


class MockDB:
    """In-memory mock for PostgresDB — stores rows as dicts."""

    def __init__(self):
        self._tables: dict[str, list[dict]] = {}
        self._id_counter = 0

    async def execute(self, sql: str, params: list | None = None):
        """Minimal mock: tracks calls, returns mock cursor for SELECTs."""
        self._last_sql = sql
        self._last_params = params
        return _MockCtx(self, sql, params)


class _MockCursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[dict]:
        return self._rows


class _MockCtx:
    def __init__(self, db: MockDB, sql: str, params):
        self._db = db
        self._sql = sql
        self._params = params

    async def __aenter__(self):
        return _MockCursor([])

    async def __aexit__(self, *args):
        pass

    def __await__(self):
        async def _noop():
            return None
        return _noop().__await__()


@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def store(mock_db):
    return CompetitionStore(mock_db)


class TestCompetitionStoreUpsertCompetitor:
    @pytest.mark.asyncio
    async def test_upsert_builds_correct_sql(self, store, mock_db):
        competitor = CompetitorCreate(
            type=CompetitorType.AGENT, name="rsi_scanner", ref_id="rsi_scanner"
        )
        await store.upsert_competitor(competitor)
        assert "INSERT INTO competitors" in mock_db._last_sql
        assert "ON CONFLICT" in mock_db._last_sql

    @pytest.mark.asyncio
    async def test_upsert_passes_correct_params(self, store, mock_db):
        competitor = CompetitorCreate(
            type=CompetitorType.MINER,
            name="miner_5DkVM",
            ref_id="5DkVM4w",
            metadata={"uid": 144},
        )
        await store.upsert_competitor(competitor)
        assert mock_db._last_params[0] == "miner"
        assert mock_db._last_params[1] == "miner_5DkVM"
        assert mock_db._last_params[2] == "5DkVM4w"


class TestCompetitionStoreGetLeaderboard:
    @pytest.mark.asyncio
    async def test_leaderboard_query_includes_joins(self, store, mock_db):
        await store.get_leaderboard(asset="BTC")
        assert "elo_ratings" in mock_db._last_sql
        assert "competitors" in mock_db._last_sql
        assert "ORDER BY" in mock_db._last_sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd trading && python -m pytest tests/unit/competition/test_store.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write store**

```python
# trading/competition/store.py
"""Database access for competition system — raw SQL via asyncpg."""
from __future__ import annotations

import json
import logging
from typing import Any

from competition.models import CompetitorCreate, LeaderboardEntry, Tier, tier_for_elo

logger = logging.getLogger(__name__)


class CompetitionStore:
    """Async database store for competition data."""

    def __init__(self, db: Any):
        self._db = db

    # ── Competitors ──

    async def upsert_competitor(self, competitor: CompetitorCreate) -> None:
        sql = """
            INSERT INTO competitors (type, name, ref_id, metadata)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (type, ref_id) DO UPDATE SET
                name = EXCLUDED.name,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """
        await self._db.execute(
            sql,
            [
                competitor.type.value,
                competitor.name,
                competitor.ref_id,
                json.dumps(competitor.metadata),
            ],
        )

    async def ensure_elo_rating(self, competitor_id: str, asset: str) -> None:
        sql = """
            INSERT INTO elo_ratings (competitor_id, asset)
            VALUES ($1, $2)
            ON CONFLICT (competitor_id, asset) DO NOTHING
        """
        await self._db.execute(sql, [competitor_id, asset])

    async def get_competitor_by_ref(self, comp_type: str, ref_id: str) -> dict | None:
        sql = "SELECT * FROM competitors WHERE type = $1 AND ref_id = $2"
        async with self._db.execute(sql, [comp_type, ref_id]) as cur:
            return await cur.fetchone()

    async def get_competitor(self, competitor_id: str) -> dict | None:
        sql = "SELECT * FROM competitors WHERE id = $1"
        async with self._db.execute(sql, [competitor_id]) as cur:
            return await cur.fetchone()

    async def list_competitors(self, comp_type: str | None = None) -> list[dict]:
        if comp_type:
            sql = "SELECT * FROM competitors WHERE type = $1 AND status = 'active' ORDER BY name"
            async with self._db.execute(sql, [comp_type]) as cur:
                return await cur.fetchall()
        sql = "SELECT * FROM competitors WHERE status = 'active' ORDER BY name"
        async with self._db.execute(sql) as cur:
            return await cur.fetchall()

    # ── Leaderboard ──

    async def get_leaderboard(
        self,
        asset: str = "BTC",
        comp_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LeaderboardEntry]:
        type_filter = "AND c.type = $4" if comp_type else ""
        params: list[Any] = [asset, limit, offset]
        if comp_type:
            params.append(comp_type)

        sql = f"""
            SELECT
                c.id, c.type, c.name, c.ref_id, c.status,
                COALESCE(r.elo, 1000) AS elo,
                COALESCE(r.tier, 'silver') AS tier,
                COALESCE(r.matches_count, 0) AS matches_count,
                COALESCE(s.current_count, 0) AS current_streak,
                COALESCE(s.best_count, 0) AS best_streak
            FROM competitors c
            LEFT JOIN elo_ratings r ON r.competitor_id = c.id AND r.asset = $1
            LEFT JOIN streaks s ON s.competitor_id = c.id AND s.asset = $1
                AND s.streak_type = 'correct_direction'
            WHERE c.status != 'retired' {type_filter}
            ORDER BY COALESCE(r.elo, 1000) DESC
            LIMIT $2 OFFSET $3
        """
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [LeaderboardEntry.from_row(row) for row in rows]

    # ── ELO ──

    async def get_elo(self, competitor_id: str, asset: str) -> int:
        sql = "SELECT elo FROM elo_ratings WHERE competitor_id = $1 AND asset = $2"
        async with self._db.execute(sql, [competitor_id, asset]) as cur:
            row = await cur.fetchone()
        return row["elo"] if row else 1000

    async def update_elo(
        self, competitor_id: str, asset: str, new_elo: int, elo_delta: int
    ) -> None:
        tier = tier_for_elo(new_elo)
        sql = """
            UPDATE elo_ratings
            SET elo = $1, tier = $2, matches_count = matches_count + 1, updated_at = NOW()
            WHERE competitor_id = $3 AND asset = $4
        """
        await self._db.execute(sql, [new_elo, tier.value, competitor_id, asset])
        # Append to history
        history_sql = """
            INSERT INTO elo_history (competitor_id, asset, elo, tier, elo_delta)
            VALUES ($1, $2, $3, $4, $5)
        """
        await self._db.execute(
            history_sql, [competitor_id, asset, new_elo, tier.value, elo_delta]
        )

    async def get_elo_history(
        self, competitor_id: str, asset: str = "BTC", days: int = 30
    ) -> list[dict]:
        sql = """
            SELECT elo, tier, elo_delta, recorded_at
            FROM elo_history
            WHERE competitor_id = $1 AND asset = $2
                AND recorded_at > NOW() - MAKE_INTERVAL(days => $3)
            ORDER BY recorded_at ASC
        """
        async with self._db.execute(sql, [competitor_id, asset, days]) as cur:
            return await cur.fetchall()

    # ── Dashboard Summary ──

    async def get_dashboard_summary(self, asset: str = "BTC") -> dict:
        leaderboard = await self.get_leaderboard(asset=asset, limit=50)
        return {
            "leaderboard": [entry.model_dump() for entry in leaderboard],
            "competitor_count": len(leaderboard),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd trading && python -m pytest tests/unit/competition/test_store.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/store.py tests/unit/competition/test_store.py
git commit -m "feat(competition): add CompetitionStore with raw SQL"
```

---

### Task 6: Competitor Registry

**Files:**
- Create: `trading/competition/registry.py`
- Create: `tests/unit/competition/test_registry.py`

- [ ] **Step 1: Write registry tests**

```python
# tests/unit/competition/test_registry.py
from __future__ import annotations

import pytest
from competition.models import CompetitorCreate, CompetitorType
from competition.registry import CompetitorRegistry


class MockStore:
    def __init__(self):
        self.upserted: list[CompetitorCreate] = []
        self.elo_ensured: list[tuple[str, str]] = []
        self._competitors: dict[tuple[str, str], dict] = {}

    async def upsert_competitor(self, competitor: CompetitorCreate) -> None:
        self.upserted.append(competitor)
        key = (competitor.type.value, competitor.ref_id)
        self._competitors[key] = {
            "id": f"id-{competitor.ref_id}",
            "type": competitor.type.value,
            "name": competitor.name,
            "ref_id": competitor.ref_id,
        }

    async def get_competitor_by_ref(self, comp_type: str, ref_id: str) -> dict | None:
        return self._competitors.get((comp_type, ref_id))

    async def ensure_elo_rating(self, competitor_id: str, asset: str) -> None:
        self.elo_ensured.append((competitor_id, asset))


SAMPLE_AGENTS_YAML = """
agents:
  - name: rsi_scanner
    strategy: rsi
    schedule: continuous
    interval: 300
    action_level: notify
  - name: funding_rate_btc
    strategy: funding_rate_arb
    schedule: continuous
    interval: 300
    action_level: suggest_trade
"""

PROVIDER_NAMES = ["on_chain", "sentiment", "anomaly", "regime"]


class TestCompetitorRegistry:
    @pytest.mark.asyncio
    async def test_register_agents_from_yaml(self):
        store = MockStore()
        registry = CompetitorRegistry(store)
        await registry.register_agents_from_yaml_str(SAMPLE_AGENTS_YAML)
        names = [c.name for c in store.upserted]
        assert "rsi_scanner" in names
        assert "funding_rate_btc" in names
        assert all(c.type == CompetitorType.AGENT for c in store.upserted)

    @pytest.mark.asyncio
    async def test_register_providers(self):
        store = MockStore()
        registry = CompetitorRegistry(store)
        await registry.register_providers(PROVIDER_NAMES)
        names = [c.name for c in store.upserted]
        assert "sentiment" in names
        assert all(c.type == CompetitorType.PROVIDER for c in store.upserted)

    @pytest.mark.asyncio
    async def test_ensure_elo_for_all_assets(self):
        store = MockStore()
        registry = CompetitorRegistry(store)
        await registry.register_providers(["sentiment"])
        # Should create ELO rows for BTC and ETH
        assets = [asset for _, asset in store.elo_ensured]
        assert "BTC" in assets
        assert "ETH" in assets
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd trading && python -m pytest tests/unit/competition/test_registry.py -v --tb=short --timeout=30`
Expected: FAIL

- [ ] **Step 3: Write registry**

```python
# trading/competition/registry.py
"""Auto-register agents, miners, and providers as competitors on startup."""
from __future__ import annotations

import logging
from typing import Any

import yaml

from competition.models import CompetitorCreate, CompetitorType
from competition.store import CompetitionStore

logger = logging.getLogger(__name__)

TRACKED_ASSETS = ["BTC", "ETH"]


class CompetitorRegistry:
    def __init__(self, store: CompetitionStore):
        self._store = store

    async def register_all(
        self,
        agents_yaml_path: str = "agents.yaml",
        provider_names: list[str] | None = None,
        miner_hotkeys: list[dict[str, Any]] | None = None,
    ) -> int:
        """Register all signal sources. Returns count registered."""
        count = 0
        # Agents from YAML
        try:
            with open(agents_yaml_path) as f:
                content = f.read()
            count += await self.register_agents_from_yaml_str(content)
        except FileNotFoundError:
            logger.warning("agents.yaml not found at %s", agents_yaml_path)

        # Providers
        if provider_names:
            count += await self.register_providers(provider_names)

        # Miners
        if miner_hotkeys:
            count += await self.register_miners(miner_hotkeys)

        logger.info("competition.registry: registered %d competitors", count)
        return count

    async def register_agents_from_yaml_str(self, yaml_str: str) -> int:
        config = yaml.safe_load(yaml_str)
        agents = config.get("agents", [])
        count = 0
        for agent_cfg in agents:
            name = agent_cfg["name"]
            competitor = CompetitorCreate(
                type=CompetitorType.AGENT,
                name=name,
                ref_id=name,
            )
            await self._store.upsert_competitor(competitor)
            await self._ensure_elo(CompetitorType.AGENT, name)
            count += 1
        return count

    async def register_providers(self, names: list[str]) -> int:
        count = 0
        for name in names:
            competitor = CompetitorCreate(
                type=CompetitorType.PROVIDER,
                name=name,
                ref_id=name,
            )
            await self._store.upsert_competitor(competitor)
            await self._ensure_elo(CompetitorType.PROVIDER, name)
            count += 1
        return count

    async def register_miners(self, miners: list[dict[str, Any]]) -> int:
        count = 0
        for miner in miners:
            hotkey = miner.get("hotkey", "")
            uid = miner.get("uid")
            short_name = f"miner_{hotkey[:8]}..."
            competitor = CompetitorCreate(
                type=CompetitorType.MINER,
                name=short_name,
                ref_id=hotkey,
                metadata={"uid": uid, "hotkey": hotkey},
            )
            await self._store.upsert_competitor(competitor)
            await self._ensure_elo(CompetitorType.MINER, hotkey)
            count += 1
        return count

    async def _ensure_elo(self, comp_type: CompetitorType, ref_id: str) -> None:
        record = await self._store.get_competitor_by_ref(comp_type.value, ref_id)
        if record:
            for asset in TRACKED_ASSETS:
                await self._store.ensure_elo_rating(str(record["id"]), asset)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd trading && python -m pytest tests/unit/competition/test_registry.py -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/registry.py tests/unit/competition/test_registry.py
git commit -m "feat(competition): add CompetitorRegistry for auto-registration"
```

---

### Task 7: API Routes + Response Schemas

**Files:**
- Create: `trading/api/routes/competition_schemas.py`
- Create: `trading/api/routes/competition.py`

- [ ] **Step 1: Write response schemas**

```python
# trading/api/routes/competition_schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field


class CompetitorResponse(BaseModel):
    id: str
    type: str
    name: str
    ref_id: str
    status: str
    elo: int
    tier: str
    matches_count: int
    streak: int = 0
    best_streak: int = 0


class LeaderboardResponse(BaseModel):
    leaderboard: list[CompetitorResponse]
    competitor_count: int


class DashboardSummaryResponse(BaseModel):
    leaderboard: list[CompetitorResponse]
    competitor_count: int


class EloHistoryPoint(BaseModel):
    elo: int
    tier: str
    elo_delta: int
    recorded_at: str


class EloHistoryResponse(BaseModel):
    competitor_id: str
    asset: str
    history: list[EloHistoryPoint]


class CompetitorDetailResponse(BaseModel):
    id: str
    type: str
    name: str
    ref_id: str
    status: str
    metadata: dict = Field(default_factory=dict)
    ratings: dict[str, dict] = Field(default_factory=dict)
```

- [ ] **Step 2: Write API routes**

```python
# trading/api/routes/competition.py
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request

from api.auth import verify_api_key
from api.routes.competition_schemas import (
    CompetitorDetailResponse,
    DashboardSummaryResponse,
    EloHistoryResponse,
    LeaderboardResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/competition", tags=["competition"])


def _get_store(request: Request):
    store = getattr(request.app.state, "competition_store", None)
    if store is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Competition system not initialized")
    return store


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    store = _get_store(request)
    data = await store.get_dashboard_summary(asset=asset)
    return DashboardSummaryResponse(**data)


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    store = _get_store(request)
    entries = await store.get_leaderboard(
        asset=asset, comp_type=type, limit=limit, offset=offset
    )
    return LeaderboardResponse(
        leaderboard=[e.model_dump() for e in entries],
        competitor_count=len(entries),
    )


@router.get("/competitors/{competitor_id}", response_model=CompetitorDetailResponse)
async def get_competitor(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    record = await store.get_competitor(competitor_id)
    if not record:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Competitor not found")
    return CompetitorDetailResponse(
        id=str(record["id"]),
        type=record["type"],
        name=record["name"],
        ref_id=record["ref_id"],
        status=record["status"],
        metadata=record.get("metadata", {}),
    )


@router.get(
    "/competitors/{competitor_id}/elo-history",
    response_model=EloHistoryResponse,
)
async def get_elo_history(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    days: int = Query(30, ge=1, le=365),
):
    store = _get_store(request)
    history = await store.get_elo_history(competitor_id, asset=asset, days=days)
    return EloHistoryResponse(
        competitor_id=competitor_id,
        asset=asset,
        history=[
            {
                "elo": h["elo"],
                "tier": h["tier"],
                "elo_delta": h["elo_delta"],
                "recorded_at": str(h["recorded_at"]),
            }
            for h in history
        ],
    )
```

- [ ] **Step 3: Register router in app.py**

In `trading/api/app.py`, find where other routers are included (search for `include_router`). Add:

```python
from api.routes.competition import router as competition_router
app.include_router(competition_router)
```

Place this near the other `include_router` calls in the `create_app()` function.

- [ ] **Step 4: Wire competition store in lifespan**

In `trading/api/app.py`, in the lifespan function, after the database is created and before `yield`, add:

```python
    # Competition system
    from competition.store import CompetitionStore
    from competition.registry import CompetitorRegistry
    competition_store = CompetitionStore(db)
    app.state.competition_store = competition_store

    if config.competition.enabled:
        registry = CompetitorRegistry(competition_store)
        provider_names = ["on_chain", "sentiment", "anomaly", "regime"]
        await registry.register_all(
            agents_yaml_path="agents.yaml",
            provider_names=provider_names,
        )
```

- [ ] **Step 5: Verify routes register**

Run: `cd trading && python -c "from api.routes.competition import router; print('Routes:', [r.path for r in router.routes])"`
Expected: Routes list including `/dashboard/summary`, `/leaderboard`, etc.

- [ ] **Step 6: Commit**

```bash
git add trading/api/routes/competition_schemas.py trading/api/routes/competition.py
git commit -m "feat(competition): add API routes for leaderboard and competitors"
```

---

### Task 8: Frontend API Client

**Files:**
- Create: `frontend/src/lib/api/competition.ts`

- [ ] **Step 1: Write the API client and TanStack hooks**

```typescript
// frontend/src/lib/api/competition.ts
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';

const tradingApi = axios.create({
  baseURL: '/api',
  headers: {
    'X-API-Key': import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : ''),
  },
});

// ── Types ──

export type CompetitorType = 'agent' | 'miner' | 'provider';
export type Tier = 'diamond' | 'gold' | 'silver' | 'bronze';

export interface Competitor {
  id: string;
  type: CompetitorType;
  name: string;
  ref_id: string;
  status: string;
  elo: number;
  tier: Tier;
  matches_count: number;
  streak: number;
  best_streak: number;
}

export interface LeaderboardResponse {
  leaderboard: Competitor[];
  competitor_count: number;
}

export interface DashboardSummary {
  leaderboard: Competitor[];
  competitor_count: number;
}

export interface EloHistoryPoint {
  elo: number;
  tier: string;
  elo_delta: number;
  recorded_at: string;
}

export interface CompetitorDetail {
  id: string;
  type: CompetitorType;
  name: string;
  ref_id: string;
  status: string;
  metadata: Record<string, unknown>;
  ratings: Record<string, Record<string, unknown>>;
}

// ── API Functions ──

export const competitionApi = {
  getDashboardSummary: (asset = 'BTC') =>
    tradingApi.get<DashboardSummary>('/competition/dashboard/summary', { params: { asset } })
      .then(res => res.data),

  getLeaderboard: (params: { asset?: string; type?: string; limit?: number; offset?: number } = {}) =>
    tradingApi.get<LeaderboardResponse>('/competition/leaderboard', { params })
      .then(res => res.data),

  getCompetitor: (id: string) =>
    tradingApi.get<CompetitorDetail>(`/competition/competitors/${id}`)
      .then(res => res.data),

  getEloHistory: (id: string, asset = 'BTC', days = 30) =>
    tradingApi.get<{ competitor_id: string; asset: string; history: EloHistoryPoint[] }>(
      `/competition/competitors/${id}/elo-history`,
      { params: { asset, days } },
    ).then(res => res.data),
};

// ── TanStack Query Hooks ──

export function useLeaderboard(asset = 'BTC', type?: string) {
  return useQuery({
    queryKey: ['competition', 'leaderboard', asset, type],
    queryFn: () => competitionApi.getLeaderboard({ asset, type }),
    refetchInterval: 30_000,
  });
}

export function useDashboardSummary(asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'dashboard', asset],
    queryFn: () => competitionApi.getDashboardSummary(asset),
    refetchInterval: 30_000,
  });
}

export function useCompetitor(id: string) {
  return useQuery({
    queryKey: ['competition', 'competitor', id],
    queryFn: () => competitionApi.getCompetitor(id),
    enabled: !!id,
  });
}

export function useEloHistory(id: string, asset = 'BTC', days = 30) {
  return useQuery({
    queryKey: ['competition', 'elo-history', id, asset, days],
    queryFn: () => competitionApi.getEloHistory(id, asset, days),
    enabled: !!id,
  });
}
```

- [ ] **Step 2: Add Vite proxy for competition routes**

In `frontend/vite.config.ts`, find the proxy config and add:

```typescript
'/api/competition': {
  target: 'http://localhost:8080',
  changeOrigin: true,
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/competition.ts
git commit -m "feat(frontend): add competition API client and TanStack hooks"
```

---

### Task 9: Frontend Components — TierBadge, StreakIndicator, CompetitorCard

**Files:**
- Create: `frontend/src/components/competition/TierBadge.tsx`
- Create: `frontend/src/components/competition/StreakIndicator.tsx`
- Create: `frontend/src/components/competition/CompetitorCard.tsx`
- Create: `frontend/src/components/competition/CompetitionErrorBoundary.tsx`

- [ ] **Step 1: Write TierBadge**

```tsx
// frontend/src/components/competition/TierBadge.tsx
import type { Tier } from '../../lib/api/competition';

const TIER_CONFIG: Record<Tier, { color: string; bg: string; label: string }> = {
  diamond: { color: '#00D4FF', bg: 'rgba(0, 212, 255, 0.15)', label: 'DIA' },
  gold:    { color: '#FFD700', bg: 'rgba(255, 215, 0, 0.15)', label: 'GLD' },
  silver:  { color: '#C0C0C0', bg: 'rgba(192, 192, 192, 0.15)', label: 'SLV' },
  bronze:  { color: '#CD7F32', bg: 'rgba(205, 127, 50, 0.15)', label: 'BRZ' },
};

export function TierBadge({ tier }: { tier: Tier }) {
  const cfg = TIER_CONFIG[tier];
  return (
    <span
      style={{ color: cfg.color, backgroundColor: cfg.bg }}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-bold"
      title={tier}
    >
      <span style={{ fontSize: '0.6rem' }}>&#9670;</span> {cfg.label}
    </span>
  );
}
```

- [ ] **Step 2: Write StreakIndicator**

```tsx
// frontend/src/components/competition/StreakIndicator.tsx
export function StreakIndicator({ streak }: { streak: number }) {
  if (streak >= 5) {
    return <span title={`${streak} win streak`}>{'🔥'} {streak}</span>;
  }
  if (streak <= -3) {
    return <span title={`${Math.abs(streak)} loss streak`}>{'❄️'} {streak}</span>;
  }
  if (streak === 0) {
    return <span className="text-gray-500">—</span>;
  }
  return <span>{streak}</span>;
}
```

- [ ] **Step 3: Write CompetitorCard (mobile layout)**

```tsx
// frontend/src/components/competition/CompetitorCard.tsx
import type { Competitor } from '../../lib/api/competition';
import { TierBadge } from './TierBadge';
import { StreakIndicator } from './StreakIndicator';

export function CompetitorCard({ competitor, rank }: { competitor: Competitor; rank: number }) {
  return (
    <div className="flex items-center gap-3 p-3 border-b border-gray-700 hover:bg-gray-800/50">
      <span className="text-gray-500 w-6 text-right text-sm">{rank}</span>
      <TierBadge tier={competitor.tier} />
      <div className="flex-1 min-w-0">
        <div className="font-medium truncate">{competitor.name}</div>
        <div className="text-xs text-gray-500">{competitor.type}</div>
      </div>
      <div className="text-right">
        <div className="font-mono font-bold">{competitor.elo}</div>
        <div className="text-xs"><StreakIndicator streak={competitor.streak} /></div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write CompetitionErrorBoundary**

```tsx
// frontend/src/components/competition/CompetitionErrorBoundary.tsx
import { Component, type ReactNode } from 'react';

interface Props { children: ReactNode }
interface State { hasError: boolean }

export class CompetitionErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-900/20 border border-red-800 rounded">
          <h3 className="font-semibold text-red-400">Competition Error</h3>
          <p className="text-red-500 text-sm">
            Unable to load competition data. The arena will retry automatically.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/competition/
git commit -m "feat(frontend): add TierBadge, StreakIndicator, CompetitorCard, ErrorBoundary"
```

---

### Task 10: Frontend LeaderboardTable + Arena Page Rewrite

**Files:**
- Create: `frontend/src/components/competition/LeaderboardTable.tsx`
- Modify: `frontend/src/pages/Arena.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Write LeaderboardTable**

```tsx
// frontend/src/components/competition/LeaderboardTable.tsx
import { useState, useEffect } from 'react';
import type { Competitor, Tier } from '../../lib/api/competition';
import { TierBadge } from './TierBadge';
import { StreakIndicator } from './StreakIndicator';
import { CompetitorCard } from './CompetitorCard';

interface LeaderboardTableProps {
  competitors: Competitor[];
  isLoading: boolean;
  onRowClick?: (id: string) => void;
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse">
      {Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3 border-b border-gray-700">
          <div className="w-6 h-4 bg-gray-700 rounded" />
          <div className="w-12 h-5 bg-gray-700 rounded" />
          <div className="flex-1 h-4 bg-gray-700 rounded" />
          <div className="w-14 h-4 bg-gray-700 rounded" />
          <div className="w-10 h-4 bg-gray-700 rounded" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-12 text-gray-500">
      <p className="text-lg mb-2">No competitors yet</p>
      <p className="text-sm">The arena awaits.</p>
    </div>
  );
}

export function LeaderboardTable({ competitors, isLoading, onRowClick }: LeaderboardTableProps) {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  if (isLoading) return <LoadingSkeleton />;
  if (!competitors.length) return <EmptyState />;

  if (isMobile) {
    return (
      <div>
        {competitors.map((c, i) => (
          <div key={c.id} onClick={() => onRowClick?.(c.id)} className="cursor-pointer">
            <CompetitorCard competitor={c} rank={i + 1} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-gray-500 border-b border-gray-700">
          <th className="py-2 px-2 text-left w-8">#</th>
          <th className="py-2 px-2 text-left w-16">Tier</th>
          <th className="py-2 px-2 text-left">Name</th>
          <th className="py-2 px-2 text-left w-14">Type</th>
          <th className="py-2 px-2 text-right w-16">ELO</th>
          <th className="py-2 px-2 text-right w-16">Streak</th>
          <th className="py-2 px-2 text-right w-16">Matches</th>
        </tr>
      </thead>
      <tbody>
        {competitors.map((c, i) => (
          <tr
            key={c.id}
            className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
            onClick={() => onRowClick?.(c.id)}
          >
            <td className="py-2 px-2 text-gray-500">{i + 1}</td>
            <td className="py-2 px-2"><TierBadge tier={c.tier} /></td>
            <td className="py-2 px-2 font-medium">{c.name}</td>
            <td className="py-2 px-2 text-gray-500 text-xs">{c.type}</td>
            <td className="py-2 px-2 text-right font-mono font-bold">{c.elo}</td>
            <td className="py-2 px-2 text-right"><StreakIndicator streak={c.streak} /></td>
            <td className="py-2 px-2 text-right text-gray-500">{c.matches_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Rewrite Arena.tsx**

Read the current `frontend/src/pages/Arena.tsx` first, then replace its content:

```tsx
// frontend/src/pages/Arena.tsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLeaderboard, type CompetitorType } from '../lib/api/competition';
import { LeaderboardTable } from '../components/competition/LeaderboardTable';
import { CompetitionErrorBoundary } from '../components/competition/CompetitionErrorBoundary';

const ASSETS = ['BTC', 'ETH'] as const;
const TYPE_FILTERS: { label: string; value: CompetitorType | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Agents', value: 'agent' },
  { label: 'Miners', value: 'miner' },
  { label: 'Providers', value: 'provider' },
];

export default function Arena() {
  const navigate = useNavigate();
  const [asset, setAsset] = useState<string>('BTC');
  const [typeFilter, setTypeFilter] = useState<CompetitorType | undefined>(undefined);
  const [isTabActive, setIsTabActive] = useState(!document.hidden);

  useEffect(() => {
    const handler = () => setIsTabActive(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  const { data, isLoading } = useLeaderboard(asset, typeFilter);

  return (
    <CompetitionErrorBoundary>
      <div className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h1 className="text-2xl font-bold">Arena Leaderboard</h1>
          <div className="flex gap-1">
            {ASSETS.map((a) => (
              <button
                key={a}
                onClick={() => setAsset(a)}
                className={`px-3 py-1 rounded text-sm ${
                  asset === a ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'
                }`}
              >
                {a}
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-1">
          {TYPE_FILTERS.map((f) => (
            <button
              key={f.label}
              onClick={() => setTypeFilter(f.value)}
              className={`px-3 py-1 rounded text-sm ${
                typeFilter === f.value ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <LeaderboardTable
          competitors={data?.leaderboard ?? []}
          isLoading={isLoading}
          onRowClick={(id) => navigate(`/arena/competitors/${id}`)}
        />

        <div className="text-xs text-gray-600 text-center">
          {data?.competitor_count ?? 0} competitors &middot; Refreshing every {isTabActive ? '30s' : '2m'}
        </div>
      </div>
    </CompetitionErrorBoundary>
  );
}
```

- [ ] **Step 3: Add competitor profile route to router.tsx**

In `frontend/src/router.tsx`, find the arena routes and add:

```typescript
{ path: 'arena/competitors/:id', element: <LazyPage><AgentProfile /></LazyPage> },
```

This reuses the existing AgentProfile page for now — Sprint 4 will extend it into a full competitor profile.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/competition/LeaderboardTable.tsx frontend/src/pages/Arena.tsx frontend/src/router.tsx
git commit -m "feat(frontend): add LeaderboardTable and rewrite Arena page"
```

---

### Task 11: Integration Smoke Test

- [ ] **Step 1: Run all competition unit tests**

Run: `cd trading && python -m pytest tests/unit/competition/ -v --tb=short --timeout=30`
Expected: All PASS

- [ ] **Step 2: Verify API routes are registered**

Run: `cd trading && python -c "
from api.routes.competition import router
for r in router.routes:
    print(f'{list(r.methods)[0]:6s} {r.path}')
"`
Expected output showing GET routes for `/api/competition/dashboard/summary`, `/api/competition/leaderboard`, etc.

- [ ] **Step 3: Verify config integration**

Run: `cd trading && python -c "
from config import load_config
c = load_config()
print('competition.enabled:', c.competition.enabled)
print('flat access:', c.competition_enabled)
"`
Expected: Both print `True`

- [ ] **Step 4: Commit all remaining changes (app.py lifespan, vite config)**

```bash
git add trading/api/app.py frontend/vite.config.ts
git commit -m "feat(competition): wire competition store into app lifespan"
```

- [ ] **Step 5: Final commit for Sprint 1**

```bash
git add -A
git commit -m "feat(competition): complete Sprint 1 — foundation"
```
