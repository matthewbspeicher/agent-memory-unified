# Schema Drift Audit

**Date:** 2026-04-05
**Purpose:** Document differences between SQLite (db.py) and Postgres (migrations.py) before consolidation

## Table Count
- SQLite (db.py): 43 tables
- Postgres (migrations.py): 43 tables
- Diff: None - table names are identical

## Known Drift

### 1. arb_spread_observations
**Status:** Columns added via migration 015_spread_locking.py

SQLite (db.py + migration 015):
```sql
is_claimed    BOOLEAN DEFAULT 0
claimed_at    TEXT
claimed_by    TEXT
```

Postgres (migrations.py base):
- ❌ Missing all three locking columns

**Fix:** Add these three columns to Postgres DDL before generating Laravel migration. The columns are critical for spread claim locking logic.

### 2. arb_trades
**Status:** Column exists in SQLite, missing in Postgres

SQLite (db.py):
```sql
sequencing TEXT NOT NULL
```

Postgres (migrations.py):
- ❌ Missing sequencing column

**Fix:** Add `sequencing` column to Postgres DDL before generating Laravel migration. This column tracks trade execution order.

### 3. JSON columns (shadow_executions, agent_registry)
**Status:** Type difference (intentional upgrade)

SQLite uses TEXT with DEFAULT '[]' or '{}':
- `shadow_executions`: opportunity_snapshot, risk_snapshot, sizing_snapshot, regime_snapshot, health_snapshot (all TEXT)
- `agent_registry`: universe, parameters, runtime_overrides, promotion_criteria, creation_context (all TEXT)

Postgres uses JSONB:
- Same columns, JSONB type with proper JSON defaults

**Fix:** Keep JSONB (better for Postgres performance and validation). Data migration script must handle TEXT→JSONB conversion by parsing JSON strings.

## Action Items

Before Laravel migration generation:
1. **Add to Postgres DDL** (trading/storage/migrations.py):
   - `arb_spread_observations`: is_claimed, claimed_at, claimed_by
   - `arb_trades`: sequencing column
2. **Verify** no other incremental migrations have been applied to SQLite that Postgres lacks
3. **Run drift audit verification** to confirm Postgres DDL matches SQLite after fixes

Data migration considerations:
1. TEXT→JSONB conversion must validate JSON strings and handle invalid JSON gracefully
2. Empty strings in SQLite JSON columns should map to empty JSON objects/arrays in Postgres
3. NULL values in TEXT columns should remain NULL in JSONB columns

## Full Table List (43 from SQLite)

1. agent_overrides
2. agent_registry
3. agent_remembr_map
4. agent_stages
5. arb_legs
6. arb_spread_observations
7. arb_trades
8. backtest_results
9. bittensor_accuracy_records
10. bittensor_derived_views
11. bittensor_miner_rankings
12. bittensor_raw_forecasts
13. bittensor_realized_windows
14. consensus_votes
15. convergence_syntheses
16. daily_briefs
17. execution_cost_events
18. execution_cost_stats
19. execution_quality
20. external_balances
21. external_positions
22. leaderboard_cache
23. llm_lessons
24. llm_prompt_versions
25. opportunities
26. opportunity_snapshots
27. performance_snapshots
28. position_exit_rules
29. risk_events
30. shadow_executions
31. signal_features
32. strategy_confidence_calibration
33. strategy_health
34. strategy_health_events
35. tournament_audit_log
36. tournament_rounds
37. tournament_variants
38. tracked_positions
39. trade_analytics
40. trade_autopsies
41. trades
42. trust_events
43. whatsapp_sessions

## Verification Commands

To re-verify this audit after fixes:

```bash
# Count tables
grep -c "CREATE TABLE IF NOT EXISTS" trading/storage/db.py
grep -c "CREATE TABLE IF NOT EXISTS" trading/storage/migrations.py

# Check arb_spread_observations has locking columns in Postgres
grep -A12 "CREATE TABLE IF NOT EXISTS arb_spread_observations" trading/storage/migrations.py | grep -E "is_claimed|claimed_at|claimed_by"

# Check arb_trades has sequencing column in Postgres
grep -A10 "CREATE TABLE IF NOT EXISTS arb_trades" trading/storage/migrations.py | grep sequencing

# Verify JSON columns are JSONB in Postgres
grep -A20 "CREATE TABLE IF NOT EXISTS shadow_executions" trading/storage/migrations.py | grep JSONB
grep -A20 "CREATE TABLE IF NOT EXISTS agent_registry" trading/storage/migrations.py | grep JSONB
```
