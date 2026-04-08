# Arena Alpha — Gamified Competition + Alpha Pipeline

**Date:** 2026-04-07
**Author:** mspeicher + Claude
**Status:** Approved

---

## Overview

Two interleaved systems that reinforce each other:

1. **Competition Core** — ELO-based ranking system where agents, Bittensor miners, and intelligence providers compete on a unified leaderboard. Tiers feed back into the consensus router (Diamond = more weight, Bronze = shadow mode).
2. **Alpha Pipeline** — Sequenced data sources and agents (CCXT, funding rates, Funding Rate Arb agent, LunarCrush, HMM regime detection, XGBoost meta-learner). Each new source enters the arena as a competitor.

Built in alternating sprints: one alpha piece, one competition piece. Every sprint delivers something visible AND something that generates better returns.

---

## Section 1: Competition Core

### Competitor Types

| Type | Source | Examples |
|------|--------|---------|
| `agent` | 15 strategy agents from agents.yaml | `rsi_scanner`, `funding_rate_btc`, `meta_agent` |
| `miner` | SN8 Bittensor miners | Identified by hotkey, UID |
| `provider` | Intelligence layer providers | `on_chain`, `sentiment`, `anomaly`, `regime`, `derivatives` |

### Match Semantics — Hybrid Baseline + Pairwise

- **Every signal** matches against a **virtual baseline competitor** ("Hodler") — ELO 1000, never changes. Buy-and-hold benchmark.
- **Pairwise matches** fire only when two competitors signal on the **same asset within a 5-minute window**. Preserves ELO semantics without O(n^2) explosion.
- **Outcome evaluation window:** configurable per match type. Default: signal's own `timeframe` (5m agent -> evaluate after 5m). Prediction market agents use contract resolution.
- **Missing price data:** match skipped, not counted as loss.
- **Draws:** both correct or both wrong -> near-zero ELO delta, scaled by magnitude difference.

### ELO Rating System

All competitors start at 1000 ELO. Separate ELO tracks per asset (BTC, ETH) plus a composite rating.

**K-Factor with Calibration Guard:**

| Confidence | Base K |
|---|---|
| High (0.8+) | 40 |
| Medium (0.5-0.8) | 20 |
| Low (<0.5) | 10 |

**Anti-gaming:** Rolling `calibration_score` (100-sample window) per competitor. If a competitor claims high confidence but hits <65% accuracy at that tier, effective confidence is **clamped down one tier** until calibration recovers. Stored in `competitors.metadata.calibration_scores`.

**Composite Rating:** Weighted average by signal count per asset. Only includes assets where `signal_count >= 5`.

```python
composite = sum(elo[asset] * signal_count[asset] for asset in assets) / total_signal_count
```

### Tier System

| Tier | ELO Range | Effect |
|------|-----------|--------|
| Diamond | 1400+ | Higher ensemble weight, featured on dashboard |
| Gold | 1200-1399 | Standard weight |
| Silver | 1000-1199 | Reduced weight |
| Bronze | < 1000 | Shadow mode — tracked but not traded on |

Tiers feed back into the consensus router. This is operational, not cosmetic.

### Achievement Definitions

| Achievement | Trigger | Scope | Min N | Rarity |
|---|---|---|---|---|
| `streak_5` / `streak_10` | 5/10 consecutive correct directional calls | Per-asset | — | Common / Rare |
| `regime_survivor` | Positive 7d rolling return spanning a regime transition (from RegimeProvider) | Per-asset | 3+ signals during window | Rare |
| `sharp_shooter` | Rolling 7d Sharpe > 2.0 | Per-asset | 10+ evaluated signals | Rare |
| `comeback_kid` | Promoted from Bronze to Gold within 14d | Composite | — | Legendary |
| `whale_whisperer` | Correct directional call within 1h of >$5M single on-chain transfer | BTC or ETH | — | Rare |
| `first_blood` | First competitor to signal opportunity yielding >1% return within evaluation window | Per-asset | Signal must precede next-closest by 2+ min | Rare |
| `iron_throne` | Hold Diamond tier for 30 consecutive days | Composite | — | Legendary |

Achievements are event-driven, checked async after each matcher batch. Progress tracking for in-progress achievements via `AchievementProgress` dataclass.

### Edge Cases

| Scenario | Handling |
|---|---|
| New competitor | ELO 1000, first 10 matches use K x 2 for fast calibration |
| Dormant (7d no signals) | ELO decays ~0.71/day toward 1000, marked "inactive" on leaderboard |
| Missing price data | Match skipped, not counted |
| Enter Bronze (ELO < 1000) | Reduced weight in consensus router, marked on leaderboard |
| Deep Bronze (ELO < 800) | Auto-shadow, notification logged, 48h grace before hard removal from consensus router |
| Competitor retired | Status -> `retired`, frozen on leaderboard with final stats, excluded from active rankings |
| Draw | ELO near-zero delta (scaled by magnitude difference) |

### Data Model

```sql
CREATE TABLE competitors (
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

CREATE TABLE elo_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id UUID REFERENCES competitors(id),
    asset VARCHAR(10) NOT NULL,
    elo INTEGER DEFAULT 1000,
    tier VARCHAR(20) DEFAULT 'silver' CHECK (tier IN ('bronze', 'silver', 'gold', 'diamond')),
    matches_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset)
);

CREATE TABLE elo_history (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID REFERENCES competitors(id),
    asset VARCHAR(10) NOT NULL,
    elo INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL,
    elo_delta INTEGER DEFAULT 0,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_elo_history_competitor ON elo_history(competitor_id, asset, recorded_at DESC);

CREATE TABLE matches (
    id BIGSERIAL PRIMARY KEY,
    competitor_a_id UUID REFERENCES competitors(id),
    competitor_b_id UUID REFERENCES competitors(id),
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
CREATE INDEX idx_matches_competitors ON matches(competitor_a_id, competitor_b_id, created_at DESC);

CREATE TABLE achievements (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID REFERENCES competitors(id),
    achievement_type VARCHAR(50) NOT NULL,
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
CREATE INDEX idx_achievements_competitor ON achievements(competitor_id, achievement_type);

CREATE TABLE streaks (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID REFERENCES competitors(id),
    asset VARCHAR(10) NOT NULL,
    streak_type VARCHAR(30) NOT NULL,
    current_count INTEGER DEFAULT 0,
    best_count INTEGER DEFAULT 0,
    last_event_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset, streak_type)
);

CREATE TABLE competition_runs (
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

### Module Layout

```
trading/competition/
  __init__.py
  engine.py          # ELO calc — pure functions, easy to test
  models.py          # Pydantic schemas + SQLAlchemy models
  registry.py        # Auto-registration of agents/miners/providers on startup
  tracker.py         # SignalBus subscriber -> outcome scoring
  matcher.py         # Hourly batch match generation + evaluation
  achievements.py    # Event-driven badge checks (async, post-match)
  leaderboard.py     # Aggregation queries, materialized view refresh
  calibration.py     # Confidence calibration tracking + clamping
  meta_learner.py    # XGBoost walk-forward (Sprint 7)
```

**Integration points:**
- `registry.py` scans `agents.yaml` + TaoshiBridge active miners + intelligence providers on startup, upserts into `competitors` table
- `tracker.py` subscribes to `SignalBus` for signal events + outcome results
- `matcher.py` runs hourly via scheduler (top of every hour)
- Leaderboard materialized view refreshes every 5 min
- New API routes: `trading/api/routes/competition.py`
- Consensus router reads tier from `elo_ratings` to weight signals

---

## Section 2: Alpha Pipeline

### 2.1 CCXT Exchange Client

Expand existing `trading/data/exchange_client.py` (currently 1.8k stub) into full async CCXT wrapper.

**Exchanges:** Binance (primary), Bybit/OKX (fallback).

**Data types:** OHLCV candles (1m/5m/1h/1d), funding rates, open interest, order book depth (top 20).

**Key decisions:**
- **Read-only** — no trading through CCXT. Execution stays with IBKR/paper trading.
- **Async** — CCXT native async, fits FastAPI event loop.
- **REST first** — start with polling. WebSocket for `watch_ohlcv` and `watch_order_book` in v2.
- **Circuit breaker** per exchange: 5 consecutive failures -> 60s cooldown. Reuses existing `intelligence/circuit_breaker.py` pattern. `ccxt.RateLimitExceeded` excluded from failure count.
- **Redis caching** by data frequency: candles 45s TTL, funding rates 4h TTL, OI 5m TTL.

**Partial failure handling** via `FetchResult` dataclass:

```python
@dataclass
class FetchResult:
    ohlcv: list[OHLCV] | None
    funding: FundingData | None
    oi: float | None
    orderbook: OrderBook | None
    errors: list[FetchError]
    timestamp: datetime

    @property
    def is_complete(self) -> bool: ...
    @property
    def partial_success(self) -> bool: ...
    def get_available_data_types(self) -> list[str]: ...
```

Downstream consumers (FundingRateArb, AnomalyProvider) check which fields are available and skip gracefully if data is missing.

**Config:**
```
STA_EXCHANGE_PRIMARY=binance
STA_EXCHANGE_FALLBACK=bybit,okx
STA_EXCHANGE_RATE_LIMIT=true
```

**Feeds into:** AnomalyProvider (fills volume/spread stubs), DerivativesDataSource, indicators.py, backtest historical data.

### 2.2 Funding Rate Data Source

`trading/data/sources/derivatives.py` — new `DerivativesDataSource`.

**Provides:**
- Current funding rate per symbol per exchange
- Annualized rate: `current * 3 * 365` (8h funding intervals, Binance standard)
- Funding rate history: 90-day internal retention, 30-day API exposure
- Open interest alongside funding
- `crowdedness_score`: `funding_rate * log(OI)` — combined metric, becomes XGBoost feature

```python
@dataclass
class FundingOISnapshot:
    symbol: str
    exchange: str
    funding_rate: float           # raw 8h rate
    annualized_rate: float        # x 3 x 365
    open_interest: float          # USD value
    oi_change_24h: float          # % change
    crowdedness_score: float      # funding * log(OI)
```

**Sign convention:** Positive funding = longs pay shorts (consistent across Binance/Bybit/OKX). Documented in code.

### 2.3 Funding Rate Arbitrage Agent

Highest-conviction new alpha (~19% annual, delta-neutral, research-backed). Already defined in `agents.yaml` as `funding_rate_btc` — needs strategy implementation.

**Strategy logic:**
1. Monitor annualized funding rates via DerivativesDataSource
2. When funding > `min_annualized_rate` (20%): LONG spot + SHORT perp (delta-neutral)
3. When funding < `exit_rate` (5%): close both legs
4. Position sized by volatility targeting (ties into later work)

**Net funding calculation:** Accounts for borrow costs on negative funding shorts.

```python
def calculate_net_funding(annualized_rate, snapshot):
    base_fee_rate = 0.0004 * 3 * 365  # 0.04% per period, annualized
    if annualized_rate > 0:
        return annualized_rate - base_fee_rate  # no borrow needed
    if not allow_negative_funding:
        return 0.0
    borrow_rate = estimate_borrow_rate(snapshot.symbol)
    return max(abs(annualized_rate) - borrow_rate - base_fee_rate, 0.0)
```

**Exchange divergence detection:** Median + 80% agreement threshold. With 3 exchanges, 2 must agree within 10% relative difference of median.

**Spike protection:** >100% annualized -> 50% position size, flagged as anomaly.

**Signal output:**

```python
@dataclass
class FundingArbSignal:
    direction: Literal["long_spot_short_perp", "short_spot_long_perp", "close"]
    expected_annualized: float
    size_multiplier: float  # 0.5 for spike, 1.0 normal
    flags: list[str]        # ["spike_anomaly", "exchange_divergence"]
    confidence: float
```

**Competition integration:** Auto-registers as `agent` competitor. Starts at ELO 1000 with K x 2 for first 10 matches.

### 2.4 LunarCrush Social Volume

Wire `STA_INTEL_LUNARCRUSH_API_KEY` (config slot already exists) into SentimentProvider as secondary source.

**Provides:** Social volume, social dominance, Galaxy Score (0-100 proprietary composite).

**Spike detection:** MAD-based (median absolute deviation) instead of mean+std to handle fat-tailed social data:

```python
def detect_social_spike(current, historical, threshold_sigma=2.5):
    median = np.median(historical)
    mad = np.median(np.abs(historical - median))
    modified_z = 0.6745 * (current - median) / mad
    return modified_z > threshold_sigma
```

**Galaxy Score thresholds:** very_bearish (0-25), bearish (25-40), neutral (40-60), bullish (60-75), very_bullish (75-100). Predictive value tracked via provider's ELO.

**Rate limits:** Free tier 30 req/min, 500/day. Aggressive caching: social volume 5min TTL, galaxy score 30min TTL, social dominance 5min TTL.

**Competition integration:** Upgrades the existing `sentiment` provider. If LunarCrush helps, sentiment's ELO rises. Built-in evaluation.

### 2.5 HMM Regime Detection

Replace heuristic `detect_regime()` with 4-state `GaussianHMM` from `hmmlearn`.

**States and agent gating:**

| State | Characteristics | Agent Gating |
|---|---|---|
| `trending_bull` | Rising prices, moderate vol | Directional agents active, arb reduced |
| `trending_bear` | Falling prices, moderate vol | Short-bias active, arb active |
| `volatile` | High vol, no direction | Directional reduced, arb + mean-reversion active |
| `quiet` | Low vol, range-bound | Mean-reversion active, momentum shadow |

**Feature vector:**
- `log_returns` — daily log returns
- `realized_volatility_20d` — 20-day rolling std * sqrt(365)
- `volume_zscore` — volume vs 20-day mean
- `funding_rate` — from DerivativesDataSource

**HMM config:** `n_components=4`, `covariance_type="full"`, `n_iter=200`, `tol=0.01`.

**Hysteresis:** `StableRegimeDetector` with 3-period minimum state duration. Pending state must persist for 3 consecutive periods before transition fires. Prevents rapid flipping at regime boundaries.

**Training:** Fit on 2 years BTC/ETH daily data. Retrain monthly. Model persisted via `joblib`.

**Competition integration:** `regime` provider competes. If HMM-gated agents outperform ungated, regime's ELO rises. Track correlation between regime_provider_ELO and avg_gated_agent_ELO — target > 0.5, investigate if < 0.3.

### 2.6 XGBoost Meta-Learner

The "coach" — learns from arena performance data to optimally combine signals. Lives in `trading/competition/meta_learner.py`.

**Feature vector (~15-20 features per sample):**
- Per-competitor: ELO, tier (encoded 0-3), streak, confidence, direction (-1/0/+1), regime fit
- Market context: regime state, regime confidence, volatility level, time of day (cyclical), days since last signal
- Cross-competitor: signal agreement ratio, ELO spread among active
- Target: actual return over evaluation window

**Walk-forward:** 30-day training window, 1-day gap, daily retrain.

**XGBoost config (overfitting protection):** `max_depth=4`, `n_estimators=100`, `learning_rate=0.1`, `subsample=0.8`, `colsample_bytree=0.8`, `reg_alpha=0.1`, `reg_lambda=1.0`, early stopping after 10 rounds.

**Auto-fallback via EnsembleRouter:**
- Starts in `baseline` mode (linear weights)
- Promotes to `meta` after 7 consecutive days of outperformance
- Demotes back to `baseline` after 3 consecutive days of underperformance (fail fast)
- **Interim fallback** (before full XGBoost): weighted average by ELO as a simpler meta-strategy

**Feature importance:** Logged per retrain cycle. Global importance displayed on dashboard (start with global, add per-competitor SHAP values in v2).

**Competition integration:** Meta-learner doesn't compete (it's the referee). But weight assignments are visible on dashboard — transparent about why it promotes/demotes signal sources.

### Dependency Graph

```
CCXT Exchange Client --> AnomalyProvider (fills stubs)
      |                --> Funding Rate Data --> Funding Rate Arb Agent
      |                         |
      |                         +--> Intelligence Layer
      |                         |
      |                         +--> crowdedness_score (XGBoost feature)
      |
      +--> Historical OHLCV --> HMM Regime Detection
                                        |
                                        +--> XGBoost Meta-Learner
                                                  ^
LunarCrush --> SentimentProvider                  |
                                           uses match data
                                           from Competition Core
```

---

## Section 3: Arena Dashboard

React 19 + Vite + TanStack Query. Builds on existing `Arena.tsx`, `ArenaGym.tsx`, `ArenaMatch.tsx`, `Leaderboard.tsx`, `AgentProfile.tsx`.

### 3.1 Global Leaderboard (`/arena`)

Unified competition view. Replaces current Arena page.

**Features:**
- Time window toggle: 1h / 24h / 7d / 30d
- Type filter tabs: All / Agents / Miners / Providers
- Tier badges: colored diamonds (Diamond blue #00D4FF, Gold #FFD700, Silver #C0C0C0, Bronze #CD7F32)
- Streak indicators: fire for hot (>= 5 correct), snowflake for cold (<= -3)
- Baseline "Hodler" row pinned at bottom — highlighted if competitors fall below
- Regime indicator pill in corner (current HMM state)
- Row highlighting: green pulse for +3 rank jump, red pulse for -3
- Tiered polling: 30s when tab active, 2min when tab blurred (via `document.visibilitychange`)

### 3.2 Competitor Profile (`/arena/:id`)

Extends existing `AgentProfile.tsx`. Full drill-down for any competitor.

**Features:**
- ELO history chart — sparkline (mobile/sidebar) or full chart with regime transition bands
- Stats panel: win rate, Sharpe, best streak, total signals, calibration score
- Achievement showcase: earned badges with dates + progress bars for in-progress achievements
- Recent match history with ELO deltas
- Calibration gauge: green (>= 0.8 "Calibrated"), yellow (>= 0.6 "Drifting"), red (< 0.6 "Unreliable")
- Meta-learner panel: current ensemble weight, weight trend, feature importance rank (global importance v1, SHAP v2)

### 3.3 Head-to-Head (`/arena/match/:a/:b`)

Builds on existing `ArenaMatch.tsx`. Direct comparison of any two competitors.

**Features:**
- Win/loss/draw record for selected window and asset
- Stats comparison: Sharpe, avg return, signals count
- Signal timeline: grouped "match moments" showing when both fired within 5min and who was right
- Timeline grouping and filtering happens backend-side to avoid sending unnecessary data

### 3.4 Achievement Feed

Live activity ticker on `/arena` sidebar. SSE-powered (not polling).

**Event types:** `achievement_earned`, `promotion`, `relegation`, `shadow_mode`, `regime_change`, `meta_learner_switch`.

**SSE implementation:** `sse-starlette` on backend. 30s heartbeat to keep connection alive. Client-side reconnect with 5s interval. Falls back to polling if SSE unavailable.

### 3.5 API Endpoints

New routes in `trading/api/routes/competition.py`. All behind existing `X-API-Key` auth.

| Method | Path | Description |
|---|---|---|
| GET | `/api/competition/dashboard/summary` | Batch: leaderboard + regime + achievements (prevents waterfall) |
| GET | `/api/competition/leaderboard` | Ranked list. Query: `window`, `asset`, `type`, `page`, `page_size` |
| GET | `/api/competition/competitors/:id` | Full profile |
| GET | `/api/competition/competitors/:id/elo-history` | Time series. Query: `days` |
| GET | `/api/competition/competitors/:id/achievements` | Earned + in-progress achievements |
| GET | `/api/competition/matches` | Recent matches. Query: `competitor_id`, `asset`, `limit` |
| GET | `/api/competition/head-to-head/:a/:b` | Direct comparison. Query: `window`, `asset` |
| GET | `/api/competition/achievements/feed` | Recent events. Query: `limit` |
| GET | `/api/competition/achievements/feed/stream` | SSE stream |
| GET | `/api/competition/meta-learner/weights` | Current weights + feature importance |
| GET | `/api/competition/regime` | Current regime state, confidence, last transition |

**Caching headers:** Leaderboard 60s, ELO history 300s, achievement feed 10s.

### 3.6 Component Structure

```
frontend/src/
  pages/
    Arena.tsx              # Rewrite — leaderboard + activity feed
    ArenaMatch.tsx         # Rewrite — head-to-head comparison
    AgentProfile.tsx       # Extend — becomes competitor profile
  components/
    competition/
      LeaderboardTable.tsx    # Sortable table with tier badges + loading skeleton + mobile cards
      EloChart.tsx            # Sparkline + full chart with regime bands
      AchievementBadge.tsx    # Badge with tooltip
      AchievementFeed.tsx     # SSE-powered activity feed
      TierBadge.tsx           # Diamond/Gold/Silver/Bronze indicator
      StreakIndicator.tsx     # Fire/snowflake with count
      RegimeIndicator.tsx     # Current regime state pill
      MetaLearnerPanel.tsx    # Weight transparency panel
      CompetitorCard.tsx      # Summary card for mobile/lists
      CalibrationGauge.tsx    # Visual calibration indicator
      SignalTimeline.tsx      # Head-to-head match moments
      CompetitionErrorBoundary.tsx  # Error boundary with fallback
    charts/
      Sparkline.tsx           # Reusable mini chart
  lib/api/
    competition.ts            # TanStack Query hooks + API client
  hooks/
    useAchievementFeed.ts     # SSE hook with reconnect
```

---

## Section 4: Implementation Sequence

### Feature Flags

All new components start disabled. Enable per-component via config.

```python
@dataclass
class CompetitionConfig:
    competition_enabled: bool = True      # Sprint 1
    elo_decay_enabled: bool = True        # Sprint 2
    funding_arb_enabled: bool = False     # Sprint 4
    hmm_regime_enabled: bool = False      # Sprint 6
    meta_learner_enabled: bool = False    # Sprint 7
    lunarcrush_enabled: bool = False      # Sprint 5
```

### Sprint 1: Foundation

**Backend:**
- DB migrations (Alembic) — all 7 competition tables
- `trading/competition/` module: `models.py`, `engine.py` (ELO pure functions)
- `registry.py` — auto-register from agents.yaml + TaoshiBridge miners + providers on startup
- `/api/competition/leaderboard` and `/api/competition/dashboard/summary` endpoints

**Frontend:**
- `LeaderboardTable.tsx` with tier badges, streak indicators, loading skeletons, error boundary
- Mobile card layout via `CompetitorCard.tsx`
- Vite proxy: `/api/competition/*` -> port 8080

**Tests:** Pydantic model validation, auto-registration integration, API 200 response.

**Delivers:** `/arena` shows all competitors listed with starting ELO.

### Sprint 2: The Game Begins

**Backend:**
- `tracker.py` — SignalBus subscriber, records signals with timestamps and confidence
- `matcher.py` — hourly batch: evaluate outcomes, generate baseline + pairwise matches, compute ELO deltas
- `calibration.py` — rolling calibration, tier clamping
- Tier promotion/relegation with 48h grace for Bronze drop
- Dormancy decay (~0.71 ELO/day toward 1000 after 7d)
- K x 2 for first 10 matches per new competitor

**Frontend:**
- Live ELO numbers updating
- Time window toggles, type filter tabs
- Row highlighting for rank changes
- Baseline Hodler row pinned at bottom

**Tests:** ELO calculation unit tests, matcher batch integration, dormancy decay edge cases, calibration clamping.

**Benchmarks:** Leaderboard API < 200ms p95. Matcher batch < 5min for 50 competitors.

**Delivers:** Arena is alive. ELO updates hourly. Competitors separate.

### Sprint 3: CCXT + Funding Rate Data

**Backend:**
- `trading/data/exchange_client.py` — full async CCXT wrapper with `FetchResult`, circuit breaker, Redis caching
- `trading/data/sources/derivatives.py` — `DerivativesDataSource` with funding, OI, `crowdedness_score`
- Wire into AnomalyProvider (fills volume/spread stubs)

**Frontend:**
- Regime indicator pill on leaderboard (existing heuristic provider)

**Tests:** CCXT mock tests, circuit breaker state transitions, cache TTL behavior, partial failure handling.

**Benchmarks:** Exchange data fetch < 2s (all 4 types). Redis cache hit rate > 80%.

**Delivers:** Real exchange data flowing. AnomalyProvider no longer stubbed. Intel enrichment immediately becomes more useful.

### Sprint 4: Funding Rate Arb Agent + Profiles

**Backend:**
- `FundingRateArbAgent` strategy implementation
- Net funding with borrow rate, exchange divergence detection, spike protection
- Auto-registration as competitor on first signal

**Frontend:**
- Competitor profile page (`/arena/:id`) — ELO chart, stats, matches, achievements (earned only)
- Calibration gauge
- Meta-learner panel placeholder

**Tests:** Funding calculation unit tests, agent signal generation integration, spike/divergence/negative funding edge cases.

**Benchmarks:** Agent signals within 1h of threshold breach. Profile page load < 1s.

**Delivers:** First new competitor enters arena at ELO 1000 with K x 2. Profiles let you drill into any competitor.

### Sprint 5: Achievements + LunarCrush

*Can split into two sub-sprints if needed (achievements first, LunarCrush second).*

**Backend:**
- `achievements.py` — full event-driven system, all 7 types, `AchievementProgress` calculation
- SSE endpoint with heartbeat and reconnect support
- LunarCrush into SentimentProvider — Galaxy Score, social volume, MAD spike detection
- Cache config for free tier limits

**Frontend:**
- Achievement feed sidebar (SSE-powered)
- Achievement progress bars on profiles
- Promotion/relegation animations

**Tests:** Achievement check unit tests per type, SSE connection/disconnection lifecycle, LunarCrush mock tests.

**Benchmarks:** Achievement feed latency < 5s. SSE stable for 1hr+.

**Delivers:** Arena gets personality. Real-time achievement ticker. Sentiment provider gets data upgrade.

### Sprint 6: HMM Regime Detection + Head-to-Head

**Backend:**
- 4-state GaussianHMM replacing heuristic `detect_regime()`
- Feature extraction (log_returns, vol_20d, volume_zscore, funding_rate)
- StableRegimeDetector hysteresis (3-period minimum)
- Model persistence with joblib, monthly retrain
- Regime transitions trigger `regime_survivor` checks
- Agent gating table per regime state

**Frontend:**
- Head-to-head page (`/arena/match/:a/:b`) with signal timeline
- Regime bands on ELO history charts
- Regime indicator shows HMM state + confidence

**Tests:** HMM training with synthetic data, stability tests (no flips within 1h), head-to-head API tests.

**Benchmarks:** HMM prediction < 100ms. Regime state stable.

**Delivers:** Context-aware competition. Regime transitions reshuffle rankings. Head-to-head comparisons.

### Sprint 7: XGBoost Meta-Learner + Polish

**Backend:**
- `WalkForwardMetaLearner` — 30-day window, daily retrain, 1-day gap
- `EnsembleRouter` with auto-fallback (7d promote, 3d demote)
- **Interim step:** weighted average by ELO as simpler meta-strategy before full XGBoost
- Feature importance logging per retrain cycle
- `/api/competition/meta-learner/weights` endpoint

**Frontend:**
- Meta-learner panel on profiles (weight, trend, importance rank)
- Mode indicator on dashboard ("Active: XGBoost" or "Active: Linear baseline")
- Feature importance bar chart
- Mobile responsive pass on all pages
- Performance optimization (materialized view tuning, query optimization)

**Tests:** Walk-forward validation, ensemble router mode switching, feature importance logging.

**Benchmarks:** Meta-learner retrain < 10min. Weight prediction < 50ms.

**Delivers:** Full system live — competition, alpha, regime detection, meta-learner all integrated and transparent on dashboard.

### What You Have at the End

- 15+ competitors battling with live ELO ratings
- 4 new data sources (CCXT, funding rates, LunarCrush, HMM regime)
- 1 new high-conviction agent (Funding Rate Arb)
- Probabilistic regime detection gating agent behavior
- XGBoost meta-learner optimally combining signals (with safe auto-fallback)
- Full arena dashboard: leaderboard, profiles, head-to-head, SSE achievement feed
- Competition tiers directly influencing trade decisions
