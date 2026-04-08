# Arena Alpha — Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a gamified ELO competition system for agents/miners/providers interleaved with an alpha pipeline (CCXT, funding rates, HMM regime, XGBoost meta-learner).

**Architecture:** Competition module (`trading/competition/`) scores signal sources via ELO, fed by SignalBus events. Alpha pipeline adds new data sources and agents that enter the arena. React dashboard surfaces it all.

**Tech Stack:** Python 3.13, FastAPI, asyncpg (raw SQL), ccxt, hmmlearn, xgboost, React 19, Vite, TanStack Query, SSE

**Spec:** `docs/superpowers/specs/2026-04-07-arena-alpha-design.md`

---

## Sprint Plans

Each sprint is a separate plan file. Execute them in order — each builds on the previous.

| Sprint | Plan File | Description |
|--------|-----------|-------------|
| 1 | `2026-04-07-arena-alpha-sprint1.md` | Foundation — DB tables, models, ELO engine, registry, leaderboard API + frontend |
| 2 | `2026-04-07-arena-alpha-sprint2.md` | Game Begins — tracker, matcher, calibration, tier logic, live leaderboard |
| 3 | `2026-04-07-arena-alpha-sprint3.md` | CCXT + Funding Rate Data — exchange client, derivatives source, AnomalyProvider wiring |
| 4 | `2026-04-07-arena-alpha-sprint4.md` | Funding Rate Arb Agent + Profiles — new agent, competitor profiles frontend |
| 5 | `2026-04-07-arena-alpha-sprint5.md` | Achievements + LunarCrush — badge system, SSE feed, social sentiment data |
| 6 | `2026-04-07-arena-alpha-sprint6.md` | HMM Regime + Head-to-Head — probabilistic regime detection, comparison UI |
| 7 | `2026-04-07-arena-alpha-sprint7.md` | XGBoost Meta-Learner + Polish — walk-forward ML, ensemble router, final polish |

## File Map (All Sprints)

### New Files

```
trading/competition/__init__.py          # Sprint 1
trading/competition/models.py            # Sprint 1 — Pydantic schemas
trading/competition/store.py             # Sprint 1 — DB access (asyncpg raw SQL)
trading/competition/engine.py            # Sprint 1 — ELO pure functions
trading/competition/registry.py          # Sprint 1 — Auto-register competitors on startup
trading/competition/tracker.py           # Sprint 2 — SignalBus subscriber
trading/competition/matcher.py           # Sprint 2 — Hourly batch match processing
trading/competition/calibration.py       # Sprint 2 — Confidence calibration tracking
trading/competition/achievements.py      # Sprint 5 — Event-driven badge system
trading/competition/meta_learner.py      # Sprint 7 — XGBoost walk-forward
trading/api/routes/competition.py        # Sprint 1 — API endpoints
trading/api/routes/competition_schemas.py # Sprint 1 — Response models
trading/data/sources/derivatives.py      # Sprint 3 — Funding rate + OI data
scripts/competition-tables.sql           # Sprint 1 — DDL for competition tables
tests/unit/competition/__init__.py       # Sprint 1
tests/unit/competition/test_engine.py    # Sprint 1
tests/unit/competition/test_models.py    # Sprint 1
tests/unit/competition/test_store.py     # Sprint 1
tests/unit/competition/test_registry.py  # Sprint 1
tests/unit/competition/test_tracker.py   # Sprint 2
tests/unit/competition/test_matcher.py   # Sprint 2
tests/unit/competition/test_calibration.py # Sprint 2
tests/unit/competition/test_achievements.py # Sprint 5
tests/unit/competition/test_meta_learner.py # Sprint 7
tests/unit/data/test_exchange_client.py  # Sprint 3
tests/unit/data/test_derivatives.py      # Sprint 3
tests/unit/agents/test_funding_arb.py    # Sprint 4
frontend/src/lib/api/competition.ts      # Sprint 1
frontend/src/components/competition/LeaderboardTable.tsx   # Sprint 1
frontend/src/components/competition/TierBadge.tsx          # Sprint 1
frontend/src/components/competition/StreakIndicator.tsx     # Sprint 1
frontend/src/components/competition/CompetitorCard.tsx      # Sprint 1
frontend/src/components/competition/CompetitionErrorBoundary.tsx # Sprint 1
frontend/src/components/competition/EloChart.tsx            # Sprint 4
frontend/src/components/competition/CalibrationGauge.tsx    # Sprint 4
frontend/src/components/competition/MetaLearnerPanel.tsx    # Sprint 4
frontend/src/components/competition/AchievementBadge.tsx    # Sprint 5
frontend/src/components/competition/AchievementFeed.tsx     # Sprint 5
frontend/src/components/competition/SignalTimeline.tsx      # Sprint 6
frontend/src/components/competition/RegimeIndicator.tsx     # Sprint 6
frontend/src/components/charts/Sparkline.tsx                # Sprint 4
frontend/src/hooks/useAchievementFeed.ts                    # Sprint 5
```

### Modified Files

```
trading/config.py                        # Sprint 1 — Add CompetitionConfig
trading/api/app.py                       # Sprint 1 — Register competition in lifespan
trading/api/routes/__init__.py           # Sprint 1 — Include competition router (if exists)
trading/agents/consensus.py              # Sprint 2 — Read tier weights from competition
trading/data/exchange_client.py          # Sprint 3 — Expand from stub to full CCXT wrapper
trading/intelligence/providers/sentiment.py # Sprint 5 — Add LunarCrush
trading/intelligence/providers/regime.py   # Sprint 6 — Replace with HMM
trading/intelligence/layer.py            # Sprint 3 — Wire derivatives provider
frontend/src/router.tsx                  # Sprint 1 — Add competition routes
frontend/src/pages/Arena.tsx             # Sprint 1 — Rewrite with leaderboard
frontend/src/pages/AgentProfile.tsx      # Sprint 4 — Extend to competitor profile
frontend/src/pages/ArenaMatch.tsx        # Sprint 6 — Head-to-head comparison
frontend/src/components/Sidebar.tsx      # Sprint 1 — Add arena link
frontend/vite.config.ts                  # Sprint 1 — Add competition proxy
```

## Key Conventions (Read Before Starting)

### Database
- Raw SQL via `asyncpg` pool (no ORM). Use `PostgresDB.execute()` which returns `_PostgresCursor`.
- Pattern: `async with db.execute(sql, [params]) as cur: rows = await cur.fetchall()`
- DDL in `scripts/competition-tables.sql`, applied manually or via entrypoint.

### Config
- All env vars use `STA_` prefix. Nested config accessed via `config.competition.enabled` or flat `config.competition_enabled`.
- New config section: add Pydantic model + register in `Config` class + add to `_NESTED_PREFIXES`.

### Routes
- Auth: `_: str = Depends(verify_api_key)`
- DI: `request.app.state.competition_store`, etc.
- Response models in separate `_schemas.py` file.

### Frontend
- `tradingApi` axios instance from `frontend/src/lib/api/bittensor.ts` (reuse for competition).
- TanStack Query for data fetching with 30s refetch interval.
- React Router v6 with lazy loading via `<LazyPage>`.

### Testing
- Tests in `tests/unit/competition/`. Run: `cd trading && python -m pytest tests/unit/competition/ -v --tb=short --timeout=30`
- Mock DB with simple dict-based store. Mock SignalBus with list collector.
- No live services needed for unit tests.
