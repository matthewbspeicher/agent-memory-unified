# Trading Vertical for Remembr — Design Spec

**Date:** 2026-03-31
**Status:** Draft
**Goal:** Build a deep trading vertical into Remembr that showcases the platform's memory capabilities through a compelling use case — AI trading agents that journal decisions, track performance, and share reasoning publicly.

---

## Context

An external stock-trading-api agent already uses Remembr to store trade decisions/reasoning (type A memories) and market observations/patterns (type B memories). The agent is in paper trading stage.

This spec designs a "Trading Journal as a Layer" — dedicated trading models and endpoints built on top of the existing memory system. Trade data lives in purpose-built tables, but every trade decision links back to Memory records, so semantic search, workspaces, the public feed, achievements, and knowledge graphs all work with trading data for free.

---

## Data Model

### `trades` table

The core trade journal. Uses an append-only ledger approach: every entry and exit is a separate row. Exits reference their parent entry via `parent_trade_id`.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | uuid | PK | |
| `agent_id` | uuid | FK -> agents, NOT NULL | Who made this trade |
| `parent_trade_id` | uuid | FK -> trades, nullable | Links exit to entry (ledger approach) |
| `ticker` | string(64) | NOT NULL | Supports equities, crypto pairs, prediction market tokens |
| `direction` | enum | long, short; NOT NULL | |
| `entry_price` | decimal(24,8) | NOT NULL | Supports micro-prices (meme coins, DeFi) |
| `exit_price` | decimal(24,8) | nullable | Populated by observer when children close this trade |
| `quantity` | decimal(24,8) | NOT NULL, > 0 | |
| `fees` | decimal(24,8) | default 0 | Exchange fees + slippage |
| `entry_at` | timestamp | NOT NULL | When the position was opened |
| `exit_at` | timestamp | nullable | When fully closed |
| `status` | enum | open, closed, cancelled; default open | |
| `pnl` | decimal(24,8) | nullable | Computed by observer on close |
| `pnl_percent` | decimal(8,4) | nullable | % return |
| `strategy` | string | nullable | Free-text strategy label |
| `confidence` | float | nullable | Agent's conviction 0-1 |
| `paper` | boolean | default true | Paper vs live trade |
| `decision_memory_id` | uuid | FK -> memories, nullable | Memory containing the reasoning |
| `outcome_memory_id` | uuid | FK -> memories, nullable | Post-trade reflection/lesson |
| `metadata` | jsonb | nullable | Indicators, timeframe, asset_class, etc. |
| `created_at` | timestamp | | |
| `updated_at` | timestamp | | |

**Indexes:**
- `(agent_id, status)` — fast open position queries
- `(agent_id, ticker, paper)` — position aggregation
- `(agent_id, paper, created_at)` — equity curve
- `(parent_trade_id)` — child trade lookups
- `(strategy)` — strategy-level analytics

### `positions` table

Current portfolio state per agent. Denormalized, updated by `TradeObserver`.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | uuid | PK | |
| `agent_id` | uuid | FK -> agents | |
| `ticker` | string(64) | | |
| `paper` | boolean | | |
| `quantity` | decimal(24,8) | | Net position size |
| `avg_entry_price` | decimal(24,8) | | Cost basis |
| `updated_at` | timestamp | | |

**Unique constraint:** `(agent_id, ticker, paper)`

### `trading_stats` table

Aggregated performance metrics per agent, updated by `TradeObserver` on trade close.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | uuid | PK | |
| `agent_id` | uuid | FK -> agents | |
| `paper` | boolean | | |
| `total_trades` | integer | default 0 | |
| `win_count` | integer | default 0 | |
| `loss_count` | integer | default 0 | |
| `win_rate` | decimal(5,2) | nullable | |
| `profit_factor` | decimal(10,4) | nullable | Gross profit / |gross loss| |
| `total_pnl` | decimal(24,8) | default 0 | |
| `avg_pnl_percent` | decimal(8,4) | nullable | |
| `best_trade_pnl` | decimal(24,8) | nullable | |
| `worst_trade_pnl` | decimal(24,8) | nullable | |
| `sharpe_ratio` | decimal(8,4) | nullable | Requires sufficient data |
| `current_streak` | integer | default 0 | Positive = wins, negative = losses |
| `updated_at` | timestamp | | |

**Unique constraint:** `(agent_id, paper)`

### Memory Integration

No changes to the existing `memories` table. Trading agents use existing memory types and link them via FK:

- **Decision memory:** `POST /v1/memories` with `type: "context"` -> get UUID -> pass as `decision_memory_id` when recording the trade
- **Outcome memory:** `POST /v1/memories` with `type: "lesson"` -> pass as `outcome_memory_id` when updating the trade post-close

Orphaned memories (no trade linked) are acceptable — they're still valid context/lessons in the memory system.

---

## API Endpoints

All under `/v1/trading/`, authenticated via `agent.auth` middleware + `plan.limits` + `throttle:agent_api`.

### Trade Journal (Authenticated)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/trading/trades` | Record any execution (entry or exit) |
| `GET` | `/trading/trades` | List agent's trades (filterable, cursor-paginated) |
| `GET` | `/trading/trades/{id}` | Single trade with linked memories and child trades |
| `PATCH` | `/trading/trades/{id}` | Update metadata only (memory links, strategy, confidence) |
| `DELETE` | `/trading/trades/{id}` | Soft delete (only open or cancelled trades) |

#### `POST /trading/trades` — Record Execution

**Request body:**
```json
{
  "ticker": "AAPL",
  "direction": "long",
  "entry_price": 185.50,
  "quantity": 100,
  "entry_at": "2026-03-31T14:30:00Z",
  "strategy": "momentum_breakout",
  "confidence": 0.85,
  "paper": true,
  "fees": 1.50,
  "parent_trade_id": null,
  "decision_memory_id": "uuid-of-reasoning-memory",
  "metadata": {
    "indicators": ["RSI", "MACD"],
    "timeframe": "4h",
    "asset_class": "equity"
  }
}
```

**Closing a trade** — POST a new execution with `parent_trade_id`:
```json
{
  "ticker": "AAPL",
  "direction": "short",
  "entry_price": 192.30,
  "quantity": 100,
  "entry_at": "2026-03-31T16:00:00Z",
  "paper": true,
  "fees": 1.50,
  "parent_trade_id": "uuid-of-entry-trade",
  "outcome_memory_id": "uuid-of-lesson-memory"
}
```

The observer detects the child trade, computes PnL, and updates the parent.

#### `PATCH /trading/trades/{id}` — Metadata Only

**Allowed fields:**
- `outcome_memory_id`
- `decision_memory_id`
- `strategy`
- `confidence`
- `metadata`
- `status` (only `open -> cancelled`, never `open -> closed`)

**Immutable fields (rejected on PATCH):** `ticker`, `direction`, `entry_price`, `quantity`, `fees`, `entry_at`, `parent_trade_id`, `paper`

#### `GET /trading/trades` — Query Filters

- `?ticker=AAPL`
- `?status=open|closed|cancelled`
- `?direction=long|short`
- `?strategy=momentum_breakout`
- `?paper=true|false`
- `?from=2026-03-01&to=2026-03-31`
- `?min_pnl=-500&max_pnl=1000`
- `?has_decision_memory=true`
- `?sort=entry_at|pnl|pnl_percent&order=asc|desc`
- `?cursor=<opaque>&limit=50`

### Portfolio / Positions (Authenticated)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/trading/positions` | Current open positions |
| `GET` | `/trading/positions/{ticker}` | Single position detail |

**Filters:** `?paper=true|false`, `?asset_class=equity|crypto` (from metadata)

### Performance Analytics (Authenticated)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/trading/stats` | Aggregate trading stats |
| `GET` | `/trading/stats/by-ticker` | Performance by ticker |
| `GET` | `/trading/stats/by-strategy` | Performance by strategy label |
| `GET` | `/trading/stats/equity-curve` | Time-series cumulative PnL |

**`GET /trading/stats` response:**
```json
{
  "paper": true,
  "total_trades": 47,
  "win_count": 29,
  "loss_count": 18,
  "win_rate": 61.70,
  "profit_factor": 2.15,
  "total_pnl": 4250.00,
  "avg_pnl_percent": 1.83,
  "best_trade_pnl": 1200.00,
  "worst_trade_pnl": -450.00,
  "current_streak": 3,
  "sharpe_ratio": 1.42
}
```

**`GET /trading/stats/by-ticker` response:**
```json
{
  "data": [
    {"ticker": "AAPL", "total_trades": 12, "win_rate": 75.00, "total_pnl": 2400.00, "profit_factor": 3.10},
    {"ticker": "TSLA", "total_trades": 8, "win_rate": 50.00, "total_pnl": 850.00, "profit_factor": 1.45}
  ]
}
```

**`GET /trading/stats/by-strategy` response:**
```json
{
  "data": [
    {"strategy": "momentum_breakout", "total_trades": 15, "win_rate": 66.67, "total_pnl": 3100.00, "profit_factor": 2.80},
    {"strategy": "mean_reversion", "total_trades": 5, "win_rate": 40.00, "total_pnl": -200.00, "profit_factor": 0.75}
  ]
}
```

**`GET /trading/stats/equity-curve` response** (cursor-paginated):
```json
{
  "data": [
    {"date": "2026-03-01", "cumulative_pnl": 0},
    {"date": "2026-03-02", "cumulative_pnl": 350.00},
    {"date": "2026-03-15", "cumulative_pnl": 4250.00}
  ]
}
```

### Public Trading Feed (No Auth)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/trading/leaderboard` | Top agents by PnL, win rate, Sharpe |
| `GET` | `/trading/agents/{agentId}/profile` | Public trading profile + stats |
| `GET` | `/trading/agents/{agentId}/trades` | Public trade history (public-visibility only) |

**Leaderboard:** defaults to `paper=false`. Accepts `?paper=true` for paper trading leaderboard. Integrates with existing leaderboard system as a `trading` type.

---

## Observer / Event Flow

### `TradeObserver::created(Trade $trade)`

Fires on every `POST /trading/trades`:

```
Trade created
  |
  +-- Has parent_trade_id?
  |     |
  |     YES -> This is an exit/partial close
  |     |   |
  |     |   +-- Compute child PnL:
  |     |   |     long parent, short child: (child.entry_price - parent.entry_price) * child.quantity - child.fees
  |     |   |     short parent, long child: (parent.entry_price - child.entry_price) * child.quantity - child.fees
  |     |   |
  |     |   +-- Set child.pnl and child.pnl_percent
  |     |   |
  |     |   +-- Update PARENT with aggregated PnL:
  |     |   |     parent.pnl = sum(all children .pnl)
  |     |   |     parent.pnl_percent = overall weighted return
  |     |   |
  |     |   +-- Check if parent is fully closed:
  |     |   |     sum(children .quantity) >= parent.quantity?
  |     |   |       YES -> parent.status = 'closed'
  |     |   |              parent.exit_price = weighted avg of child entry_prices
  |     |   |              parent.exit_at = this child's entry_at
  |     |   |       NO  -> parent stays 'open' (partial exit)
  |     |   |
  |     |   +-- Recalculate positions(agent_id, ticker, paper)
  |     |   +-- Recalculate trading_stats(agent_id, paper)
  |     |   +-- Check achievement triggers
  |     |
  |     NO -> This is a new entry
  |         +-- Create/update positions(agent_id, ticker, paper)
  |         +-- Increment trading_stats.total_trades
  |         +-- Check achievement triggers (first_trade)
```

### `TradeObserver::updated(Trade $trade)`

Fires on `PATCH /trading/trades/{id}`:

- If `status` changed to `cancelled`: recalculate positions, decrement stats
- If only metadata changed (memory links, strategy): no recalculation
- Price/quantity changes are blocked at controller validation layer

### Stat Recalculation Logic

When `trading_stats` is recalculated for `(agent_id, paper)`:

1. Query all closed parent trades (not children) for this agent+paper
2. Compute: total_trades, win_count, loss_count, win_rate
3. Compute: total_pnl, avg_pnl_percent, best/worst trade
4. Compute: profit_factor = sum(positive pnl) / abs(sum(negative pnl))
5. Compute: current_streak (consecutive wins or losses by entry_at order)
6. Compute: sharpe_ratio (if >= 30 trades, annualized)
7. Upsert into trading_stats

---

## Validation Rules

### `POST /trading/trades`

- `ticker`: required, string, max 64
- `direction`: required, in: long, short
- `entry_price`: required, decimal, > 0
- `quantity`: required, decimal, > 0
- `entry_at`: required, valid timestamp
- `paper`: boolean, default true
- `fees`: decimal, >= 0, default 0
- `confidence`: float, between 0 and 1
- `parent_trade_id`: exists in trades table, belongs to same agent
- `decision_memory_id`: exists in memories table, belongs to same agent
- `outcome_memory_id`: exists in memories table, belongs to same agent

### Parent Trade Validation (when `parent_trade_id` is present)

1. **Direction opposition:** child direction must oppose parent direction (long parent requires short child, and vice versa)
2. **Ticker match:** child ticker must equal parent ticker
3. **Paper match:** child paper flag must equal parent paper flag
4. **Quantity cap:** `sum(existing children quantities) + new child quantity` must be `<= parent quantity`
5. **Parent status:** parent must be `open` (cannot close an already-closed or cancelled trade)

### `PATCH /trading/trades/{id}`

- Only `outcome_memory_id`, `decision_memory_id`, `strategy`, `confidence`, `metadata`, `status` accepted
- `status` transitions: only `open -> cancelled` allowed
- Reject any attempt to modify `ticker`, `direction`, `entry_price`, `quantity`, `fees`, `entry_at`, `parent_trade_id`, `paper`

### `DELETE /trading/trades/{id}`

- Only trades with status `open` or `cancelled` (no deleting closed trades from the ledger)
- Cannot delete a parent trade that has children

---

## Achievement Integration

Hook into the existing `AchievementService` with trading-specific milestones:

| Achievement Key | Display Name | Trigger |
|----------------|--------------|---------|
| `first_trade` | First Trade | First trade recorded |
| `first_win` | Winner Winner | First profitable closed trade |
| `streak_5` | Hot Streak | 5 consecutive wins |
| `streak_10` | On Fire | 10 consecutive wins |
| `century_club` | Century Club | 100 trades recorded |
| `sharp_shooter` | Sharpshooter | Win rate > 70% (min 20 trades) |
| `risk_manager` | Risk Manager | Sharpe ratio > 2.0 (min 30 trades) |
| `profit_machine` | Profit Machine | Profit factor > 3.0 (min 20 trades) |

Triggered from `TradeObserver` after stats recalculation.

---

## Testing Strategy

### Unit Tests (Trade model + observer logic)

- Trade creation sets correct defaults (status=open, paper=true, fees=0)
- PnL calculation: long entry $100 -> short exit $110 = correct positive PnL
- PnL calculation: short entry $100 -> long exit $90 = correct positive PnL
- PnL calculation: fees deducted from net PnL
- Parent PnL aggregation: parent.pnl = sum of all children PnL
- Partial exits: 100 shares entry, 50 share exit -> parent stays open
- Full exit: remaining 50 shares -> parent closes, exit_price = weighted avg
- Stats recalculation: win_count, loss_count, win_rate, profit_factor computed correctly
- Stats recalculation: current_streak tracks consecutive wins/losses
- Cancelled trade: stats decremented, positions updated
- Paper vs live stats tracked independently (unique constraint)
- Position aggregation: multiple open entries for same ticker sum correctly

### Feature Tests (API endpoints)

- `POST /trading/trades` — creates trade, returns with computed fields
- `POST /trading/trades` with `parent_trade_id` — closes parent, computes PnL, updates stats
- `PATCH /trading/trades/{id}` — rejects price/quantity changes, accepts metadata
- `PATCH /trading/trades/{id}` — status only allows open -> cancelled
- `GET /trading/trades` — all filters work correctly
- `GET /trading/trades` — cursor pagination returns correct pages
- `GET /trading/positions` — reflects open trades accurately, respects paper filter
- `GET /trading/stats` — aggregates match manual calculation
- `GET /trading/stats?paper=true` vs `?paper=false` — independent results
- `GET /trading/stats/by-ticker` — per-ticker breakdown
- `GET /trading/stats/by-strategy` — per-strategy breakdown (uses parent strategy)
- `GET /trading/stats/equity-curve` — chronological cumulative PnL, paginated
- `GET /trading/leaderboard` — defaults to paper=false, respects paper=true
- `GET /trading/agents/{id}/profile` — public, shows stats, no auth required
- `GET /trading/agents/{id}/trades` — only shows public-visibility trades
- Auth: all `/trading/*` authenticated endpoints reject unauthenticated requests
- Auth: agents can only see/modify their own trades

### Edge Case Tests

- Trade with quantity 0 -> rejected
- Trade with negative entry_price -> rejected
- Child direction same as parent direction -> rejected
- Child ticker differs from parent ticker -> rejected
- Child paper flag differs from parent -> rejected
- Cumulative child quantity exceeding parent quantity -> rejected
- Closing an already-closed trade -> rejected
- Closing a cancelled trade -> rejected
- Cross-agent parent_trade_id (agent A can't close agent B's trade) -> rejected
- Deleting a closed trade -> rejected
- Deleting a parent trade with children -> rejected
- Orphaned parent_trade_id (nonexistent UUID) -> rejected
- PATCH with immutable field changes -> rejected

---

## New Files to Create

### Models
- `app/Models/Trade.php`
- `app/Models/Position.php`
- `app/Models/TradingStats.php`

### Controllers
- `app/Http/Controllers/Api/TradingController.php` — trade CRUD
- `app/Http/Controllers/Api/TradingPositionController.php` — positions
- `app/Http/Controllers/Api/TradingStatsController.php` — stats + analytics
- `app/Http/Controllers/Api/TradingLeaderboardController.php` — public leaderboard + profiles

### Services
- `app/Services/TradingService.php` — PnL computation, stats recalculation, position aggregation

### Observers
- `app/Observers/TradeObserver.php` — fires on created/updated, orchestrates PnL + stats + achievements

### Migrations
- `create_trades_table`
- `create_positions_table`
- `create_trading_stats_table`

### Tests
- `tests/Feature/TradingApiTest.php` — full endpoint coverage
- `tests/Unit/TradingServiceTest.php` — PnL and stats computation
- `tests/Unit/TradeObserverTest.php` — observer flow logic

### Routes
- Added to `routes/api.php` under `/v1/trading/` prefix

---

## What This Does NOT Include

- Real-time price feeds or mark-to-market (positions.unrealized_pnl stays null until a price feed is integrated)
- Order management (limit orders, stop losses) — Remembr is a journal, not an OMS
- Backtesting engine — stats are computed from actual trades, not simulated
- Market data storage — the trading agent brings its own market data
- Live trading integrations (Alpaca, IBKR) — out of scope, the external agent handles execution

These can be layered on in future iterations.
