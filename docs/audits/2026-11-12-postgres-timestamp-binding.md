# PostgreSQL timestamp binding audit

**Date:** 2026-11-12. **Scope:** every SQL statement in `trading/` outside tests. **Read-only:** no source was changed.

## Status: fixed in the facade

The write side is fixed in `trading/storage/postgres.py`. The facade converts a date or time argument the driver refuses (ISO text, or an aware datetime for a `TIMESTAMP` column) and remembers the conversion for that statement. Bound through the facade, all 108 parameters below now accept text. `executemany` is not covered.

The read side was then audited, because writes that succeed fill columns whose readers expected text:

- **Fixed:** 15 readers that parsed a stored time with `datetime.fromisoformat` or compared it as a string now use `trading/storage/temporal.py`. They are in `storage/performance.py`, `storage/bittensor.py` (6), `execution/shadow.py`, `learning/strategy_health.py`, `learning/confidence_calibration.py`, `analytics/strategy_scorecard.py`, `journal/service.py`, `journal/autopsy.py`, `api/routes/signal_features.py`, `leaderboard/engine.py`, `storage/external.py` and `strategies/portfolio.py`.
- **Fixed:** facade rows can be read by position as well as by name. Stores written for SQLite read `row[0]`, which raised `KeyError` on PostgreSQL in `storage/spreads.py`, `brief/generator.py`, `warroom/engine.py`, `storage/external.py`, `learning/optimizer.py` and `learning/tournament.py`.
- **Fixed:** `storage/trade_csv.py` (`TaxExporter.export_tax_report`) unpacked a row into variables, which yields column names on PostgreSQL and values on SQLite.
- **Fixed:** `integrations/bittensor/evaluator.py` compared bar times with a window's collection time. Tradier and Bitget bars had no zone and the collection time has one, so the comparison raised on either backend. It now compares instants, and Bitget bars carry UTC instead of the host's local time. A window is skipped when the bar history starts after the window was collected, so late-starting history is not scored as if it were the forecast period.
- **Still open:** bar sources that return a different bar size than asked for, or times in an exchange's local zone. Tradier maps `5m` to daily bars and IBKR's intraday times are in the gateway's local zone; both are read as UTC. They only reach the evaluator when that broker is primary and Yahoo fails.
- **Done since:** the engine's pool now starts every session in UTC (`server_settings={"TimeZone": "UTC"}` in `DatabaseConnection.connect`), so `NOW()` and column defaults write UTC into `TIMESTAMP` columns, as the stores do. See [the audit](2026-11-12-postgres-utc-sessions.md). Rows written earlier from the server's clock, by a column default or by `datetime('now')` in a statement (opportunities, overrides, tournament, `llm_lessons.archived_at`), are not rewritten. If the live role's zone was not UTC, those values stay in that zone and now read as offset by it: for example, the delayed opportunity listing would hold older rows back longer (zone east of UTC) or release them early (west) for a period equal to the offset. If the zone was already UTC, nothing changes. Maintenance scripts with their own connections are not pinned.
- **Still open:** a naive `datetime` object bound to a `TIMESTAMPTZ` column is read by the driver as the host's local time, while naive text is read as UTC. `competition/store.py` binds `datetime.utcnow()` this way.
- **Not traced:** `events/publisher.py`, `data/redis_bridge.py`, `scripts/`, and `storage/arbitrage.py` (already has its own handling).

The findings below are as they were before the fix.

## Finding

On a PostgreSQL database with the column types of `scripts/init-trading-tables.sql`, **51 call sites in 21 files** bind a value the driver refuses for a date or timestamp parameter. One of them is a fallback attempt that is caught and then succeeds; the other 50 are refused with nothing after them that works. The same bug was fixed for `OpportunityStore.save` in pull request 11.

- **49 sites bind text** (usually `.isoformat()`, or a parameter annotated `str`) where the column is `DATE`, `TIMESTAMP` or `TIMESTAMPTZ`.
- **2 sites bind a time-zone-aware datetime** to a `TIMESTAMP` column, which has no time zone. Both are in `brief/session_bias.py`, in `generate`, where all three attempts are refused.
- **32 sites are fine.** They bind a naive UTC datetime or a date, or already branch on the backend.

SQLite accepts all of these, so no unit test sees them.

## The one thing this depends on

Whether this bites depends on the column types the real database has, and I did not look at any real database. The repository defines the tables twice: the script uses `TIMESTAMP` and `JSONB`, and `_INIT_DDL` in `trading/storage/db.py` uses `TEXT`. On `TEXT` columns the text bindings work, and it is the sites that pass datetimes that fail instead.

The engine cannot create its tables on an empty PostgreSQL (see the plan document's follow-ups), so a working database most likely came from the script. This query settles it:

```sql
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name IN ('created_at', 'updated_at', 'expires_at', 'voted_at', 'observed_at', 'timestamp')
ORDER BY 1, 2;
```

## What the driver accepts

Measured by binding each kind of value at all 108 date and timestamp parameters, inside transactions that were rolled back:

| Column type | Parameters | Text | Aware datetime | Naive datetime | Date |
|---|---|---|---|---|---|
| `DATE` | 18 | refused | accepted | accepted | accepted |
| `TIMESTAMP` | 64 | refused | refused | accepted | accepted |
| `TIMESTAMPTZ` | 26 | refused | accepted | accepted | accepted |

asyncpg refuses while encoding the arguments, so a refused statement is never run.

## Confirmed by calling the real code

Three store methods called against the disposable database:

| Call | Result |
|---|---|
| `ConsensusStore.add_vote` | raised `DataError` on argument 5 |
| `StrategyHealthStore.upsert_status` | raised `DataError` on argument 17 |
| `SpreadStore.record` | returned `None`; the `DataError` is caught and logged as non-fatal |

`SpreadStore.record` matters most of the three: its own docstring says returning `None` silently breaks the path from spread observation to arbitrage execution. The other 48 sites were classified from the code and not called. Whether each raises or is swallowed by its caller was not checked.

## Sites that are refused

**`api/routes/backtest.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 102 | `run_backtest` | date | `result.run_date.isoformat(); str(result.data_start); str(result.data_end)` | text |
| 207 | `run_sandbox` | date | `req.period (a string such as a period name)` | text |

**`brief/generator.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 52 | `get_or_generate` | date | `today` | text |
| 66 | `get_or_generate` | date, timestamp | `today; now` | text |

**`brief/session_bias.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 137 | `get_active_bias` | date | `today_iso` | text |
| 199 | `generate` | date, timestamp | `now_dt; today_date` | aware datetime into a column without a time zone |
| 206 | `generate` | date, timestamp | `today; now_dt.isoformat()` | text |
| 211 | `generate` | date, timestamp | `now_dt; today_date` | aware datetime into a column without a time zone |

**`leaderboard/engine.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 208 | `save_cache` | timestamp | `snapshot_ts; now` | text |

**`learning/optimizer.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 78 | `save_result` | date | `result.run_date.isoformat(); result.data_start.isoformat(); result.data_end.isoformat()` | text |

**`learning/tournament.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 35 | `start_round` | timestamp | `started_at` | text |
| 178 | `complete_round` | timestamp | `ended_at` | text |

**`reports/digest.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 18 | `generate_daily_digest` | timestamp | `today_str` | text |
| 26 | `generate_daily_digest` | timestamp | `today_str` | text |
| 32 | `generate_daily_digest` | timestamp | `today_str` | text |

**`storage/bittensor.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 27 | `save_raw_forecasts` | timestamp | `r.collected_at.isoformat()` | text |
| 115 | `save_derived_view` | timestamp | `view.timestamp.isoformat()` | text |
| 160 | `expire_stale_windows` | timestamp | `cutoff.isoformat()` | text |
| 195 | `get_view_history` | timestamp | `since.isoformat()` | text |
| 246 | `get_unevaluated_windows` | timestamp | `cutoff_param` | text |
| 282 | `save_realized_window` | timestamp | `realized.captured_at.isoformat()` | text |
| 320 | `save_accuracy_records` | timestamp | `rec.evaluated_at.isoformat()` | text |
| 540 | `update_miner_ranking` | timestamp | `ranking.updated_at.isoformat()` | text |
| 644 | `save_weight_set_log` | timestamp | `attempted_at.isoformat()` | text |

**`storage/consensus.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 20 | `add_vote` | timestamp | `voted_at.isoformat()` | text |
| 29 | `get_votes` | timestamp | `cutoff.isoformat()` | text |
| 45 | `cleanup_expired` | timestamp | `cutoff.isoformat()` | text |

**`storage/execution_costs.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 91 | `list_events` | timestamp | `window_start: str` | text |

**`storage/execution_quality.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 22 | `save` | timestamp | `fill.filled_at.isoformat()` | text |

**`storage/external.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 34 | `import_positions` | timestamp | `imported_at` | text |
| 56 | `import_positions` | timestamp | `imported_at` | text |

**`storage/performance.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 39 | `save` | timestamp | `ts.isoformat()` | text |

**`storage/pnl.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 72 | `open_position` | timestamp | `entry_time; expires_at` | text |
| 81 | `open_position` | timestamp | `entry_time; expires_at` | text |
| 103 | `close_position` | timestamp | `exit_time` | text |
| 159 | `list_closed` | timestamp | `since: str` | text |
| 441 | `_apply_fill` | timestamp | `stamp` | text |

**`storage/shadow.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 200 | `mark_resolved` | timestamp | `resolved_at` | text |

**`storage/signal_features.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 98 | `list_by_agent` | timestamp | `start / end: str` | text |
| 127 | `list_by_symbol` | timestamp | `start / end: str` | text |
| 162 | `list_filtered` | timestamp | `start / end: str` | text |

**`storage/spreads.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 61 | `record` | timestamp | `obs.observed_at: str (ISO text by default)` | text |
| 98 | `get_history` | timestamp | `cutoff` | text |

**`storage/strategy_health.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 73 | `upsert_status` | timestamp | `cooldown_until; updated_at` | text |
| 140 | `record_event` | timestamp | `created_at` | text |

**`storage/trade_analytics.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 61 | `list_by_strategy` | timestamp | `window_start: str` | text |
| 102 | `list_all` | timestamp | `window_start: str` | text |

**`warroom/engine.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 84 | `detect_convergences` | timestamp | `cutoff` | text |
| 240 | `get_synthesis` | timestamp | `datetime.utcnow().isoformat()` | text |
| 255 | `get_timeline` | timestamp | `cutoff` | text |

**`whatsapp/client.py`**

| Line | Function | Column type | Bound value | Why refused |
|---|---|---|---|---|
| 57 | `persist_session` | timestamp | `ts.isoformat()` | text |

Notes on this table:

- `brief/session_bias.py:137` is the middle of three attempts in `get_active_bias`. It is refused and caught, and the third attempt binds a date and works.
- A parameter annotated `str` is counted as text. A caller that passes a datetime anyway would change the verdict for that site.
- `api/routes/backtest.py:207` binds `req.period` to two `DATE` columns. That looks wrong on any backend, not only PostgreSQL.

## Sites that are fine

| Site | Column type | Bound value |
|---|---|---|
| `brief/session_bias.py:130` | date | date object, after two refused attempts |
| `brief/session_bias.py:143` | date | today |
| `brief/session_bias.py:152` | date | fetchrow branch, not reachable on the facade |
| `competition/store.py:195` | timestamptz | cutoff |
| `competition/store.py:777` | timestamptz | naive UTC datetime |
| `competition/store.py:828` | timestamptz | datetime.utcnow() |
| `competition/store.py:946` | timestamptz | naive UTC datetime |
| `competition/store.py:1238` | timestamptz | datetime.utcnow() |
| `competition/store.py:1359` | timestamptz | datetime.utcnow() |
| `competition/store.py:1372` | timestamptz | datetime.utcnow() |
| `competition/store.py:1438` | timestamptz | now |
| `competition/store.py:1500` | timestamptz | datetime.utcnow() |
| `feeds/health_monitor.py:289` | timestamptz | threshold_param |
| `feeds/health_monitor.py:291` | timestamptz | threshold_param |
| `feeds/pnl_attribution.py:314` | timestamptz | now_param |
| `feeds/pnl_attribution.py:338` | timestamptz | now_param |
| `feeds/pnl_attribution.py:522` | timestamp | made naive UTC first |
| `feeds/pnl_attribution.py:524` | timestamp | made naive UTC first |
| `feeds/pnl_attribution.py:656` | timestamptz | now_param |
| `feeds/pnl_attribution.py:664` | timestamptz | now_param |
| `feeds/pnl_attribution.py:737` | timestamptz | now_param |
| `feeds/pnl_attribution.py:739` | timestamptz | now_param |
| `feeds/pnl_attribution.py:786` | timestamptz | ts_param |
| `feeds/publisher.py:271` | timestamptz | datetime on PostgreSQL, text on SQLite |
| `storage/arbitrage.py:36` | timestamp | _created; _updated |
| `storage/arbitrage.py:95` | timestamp | now |
| `storage/arbitrage.py:142` | timestamp | now |
| `storage/opportunities.py:132` | timestamp | fixed in pull request 11 |
| `storage/opportunities.py:291` | timestamp | the value read back from the same column |
| `storage/shadow.py:146` | timestamptz | cutoff |
| `storage/shadow.py:149` | timestamp | cutoff |
| `storage/spreads.py:219` | timestamp | now |

## Method

1. **Extract.** An AST pass over `trading/` found 471 call sites that send a `SELECT`, `INSERT`, `UPDATE`, `DELETE` or `WITH` statement, with the expressions bound to each.
2. **Build the schema.** A disposable PostgreSQL 17 container was loaded with `scripts/init-trading-tables.sql`, `scripts/competition-tables.sql`, `scripts/migrations/*.sql`, `init_db_postgres`, `PaperStore.init_tables` and `TrackedPositionStore.init_tables`. That gave 85 tables.
3. **Type.** Each statement was translated with `PostgresDB._translate` and prepared; PostgreSQL reported the type of every parameter. 366 statements prepared.
4. **Classify.** Each date or timestamp parameter was matched to the expression bound to it. 83 were classified automatically and 25 by reading the code.
5. **Confirm.** The driver's behaviour was measured at every such parameter, and three store methods were called for real.

The container was removed afterwards. No real database, broker or service was touched.

## What this audit does not cover

- **Reads.** A `TIMESTAMP` column returns a `datetime`, where SQLite returns text. Code that parses or compares the value as a string would break in the other direction. Not audited.
- **77 statements that did not prepare.** Most use tables that none of the sources above create: `paper_fill_jobs` (17), `memories` (10), `match_bets` (9), `identity.agent_drafts` (6), `correlation_snapshots` (3), `users` (3), `paper_auto_ticks` (2), `paper_entry_exit_handoffs` (2), `agents` (1). Thirteen use a column the schema lacks, for example `consensus_votes.weight` in `agents/consensus.py:134` and `tracked_positions.legacy_entry_quantity` in `storage/pnl.py:213`. Four, including three in `storage/memory.py`, are not valid PostgreSQL after translation, and one has a parameter PostgreSQL cannot type. Each of these is its own question; they are listed here because the audit found them, not because they were investigated.
- **33 statements built with f-strings and 16 whose SQL could not be resolved statically.** They are in `storage/bittensor.py`, `storage/confidence_calibration.py`, `storage/knowledge_graph.py`, `storage/agent_registry.py`, `storage/decay_scheduler.py`, `warroom/engine.py`, `api/routes/feeds.py` and `api/app.py`, among others.
- **Other type mismatches.** Booleans bound as integers, JSON and numeric columns were not checked.
- **`executemany` argument lists.**

## Recommendation

Fix this once, in the `PostgresDB` facade, instead of at 50 sites. The codebase already has four different local workarounds: `is_postgres` branches in `feeds/`, `.replace(tzinfo=None)` in `storage/arbitrage.py` and `storage/spreads.py`, `_coerce_datetime_param` in `storage/shadow.py`, and the retry in `storage/opportunities.py`.

The facade can prepare each statement, read the parameter types PostgreSQL reports, and convert only the parameters typed as date or timestamp: ISO text to a datetime or date, and aware datetimes to naive UTC for `TIMESTAMP`. That is deterministic, needs no error matching, and changes nothing for statements that work today. asyncpg already prepares every parameterised statement, so it should add no round trip, but that needs measuring with the production pool settings (`statement_cache_size=0`).

Two things should come first:

1. Run the query above against the real database, so the fix targets the schema that exists.
2. Audit the read side for the same tables, because a write that starts succeeding puts values into columns whose readers have never seen them populated.
