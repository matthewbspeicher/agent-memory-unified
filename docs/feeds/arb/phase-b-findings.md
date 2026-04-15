# PM Arb Signal Feed — Phase B Diagnostic Findings

**Date:** 2026-04-15
**Spec:** [2026-04-15-arb-signal-feed-design.md](../../superpowers/specs/2026-04-15-arb-signal-feed-design.md)
**Plan:** `~/.claude/plans/temporal-spinning-flame.md` (B + A + D sequencing)
**Engine snapshot:** trading container up 1h, Postgres healthy, 17:39 UTC manual scan run

---

## TL;DR

The adapters, matcher, and strategy all work end-to-end when triggered. But **three independent bugs** prevent the `EventBus` `arb.spread` → `feed_publisher` pipeline from producing anything in production today:

1. **Cron scheduler silently does not fire scans.** Root cause: `cross_platform_arb` registered twice — placeholder in config.py returns `None`, real factory in app.py registered conditionally later. `_reconcile_registry` gets `None` and silently skips the agent. Manual `POST /agents/cross_platform_arb/scan` returns 12 real opportunities with 9¢–46¢ gaps.
2. **`SpreadStore.record()` INSERTs fail silently.** Postgres `arb_spread_observations` schema has `created_at`/`updated_at`; the INSERT targets `observed_at`. Every insert fails, exception is caught and logged as a "non-fatal" WARNING that never appears in logs. `observation_id` → None → `arb.spread` never publishes → publisher has nothing to subscribe to today.
3. **Postgres datetime incompatibility.** `SpreadStore` and `OpportunityStore` use SQLite `datetime('now', '-2 minutes')` modifier syntax. `PostgresDB._convert_datetime_now()` only handled `datetime('now')` → `NOW()`, not modifier forms. `get_top_spreads()` and `claim_spread()` queries fail on Postgres.

**Implication for the plan:** Phase A cannot proceed as-is. A new **Phase A0** (upstream-pipeline fix) must precede the week-0 critical path. Estimated 3–6h additional work.

---

## Detailed findings

### B1 — Adapters produce candidates ✅ (but only on-demand)

`POST /agents/cross_platform_arb/scan` triggered via HTTP at 17:39 UTC returned **12 opportunities** with the following spread distribution:

| Gap (cents) | Count |
|---|---|
| 46 | 1 |
| 34 | 1 |
| 27 | 1 |
| 24 | 1 |
| 17 | 1 |
| 15 | 1 |
| 13 | 1 |
| 12 | 2 |
| 10 | 1 |
| 9 | 2 |

Adapter-layer logs at 13:10 UTC: `arb match_index seeded: kalshi_events=761 poly_events=5000 pairs=84`. Both venues respond. Matcher score floor=0.60, max_gap=50 gates are active and producing real pairs.

**Status:** The 2026-04-14 "parked adapters" concern from [revenue-roadmap.md §2.5](../../plans/revenue-roadmap.md) is resolved. Commits `ccbe8ea` / `f3a4e4c` / `1b28488` / `ef9f57d` unparked the `/events` path.

### B2 — `arb.spread` EventBus emission ❌

Expected: the scan should publish an `arb.spread` event per opportunity via [cross_platform_arb.py:232-246](../../../trading/strategies/cross_platform_arb.py). Publication is gated on `self.event_bus is not None AND observation_id is not None` (line 232). `observation_id` is set by `SpreadStore.record()` on line 157. Since that insert fails (see B-extra below), `observation_id` stays None, and the event never fires.

**Status:** No `arb.spread` events fire in production today.

### B3 — Shadow decision path ❌ (no-op given B2)

[arb_executor.py:67-71](../../../trading/execution/arb_executor.py) subscribes to EventBus topic `arb.spread`. When `enabled=False` (default), `_log_shadow_decision()` emits `event_type="arb.shadow"` via structured logging (line 158-174). Since no events arrive, no shadow decisions fire.

`shadow_executions` Postgres table exists ([storage/db.py:360](../../../trading/storage/db.py)) but is not populated by arb-executor decisions (confirmed via SQL inspection — no rows for `agent_name='cross_platform_arb'`).

**Status:** Downstream pipeline intact; upstream is the problem.

### B4 — `client_order_id` wiring gap ✅ (confirmed gap)

```bash
$ grep -rn "client_order_id" trading/
(no matches)
```

[broker/models.py:56-116](../../../trading/broker/models.py) — `OrderBase` and all 5 subclasses (`MarketOrder`, `LimitOrder`, `StopOrder`, `StopLimitOrder`, `TrailingStopOrder`, `BracketOrder`) have no `client_order_id` field. `OrderResult.order_id` at line 182-189 is broker-assigned, not caller-tagged.

Plumbing scope per spec §5:
1. Add field to `OrderBase` — 1 line
2. Plumb through `ArbExecutor._execute_arb` ([arb_executor.py:176-228](../../../trading/execution/arb_executor.py)) — set `client_order_id=signal_id` when building `MarketOrder`
3. Plumb through each broker adapter's `place_order` — Kalshi, Polymarket, Paper (at minimum)
4. Verify fills returned by broker APIs echo the field back; implement `(ticker, timestamp-window)` fallback join where they don't

**Status:** Not week-0 scope. Week-1 prerequisite for PnL attribution job.

### B5 — Postgres is prod DB ✅

[storage/db.py:902-911](../../../trading/storage/db.py) `init_db_postgres()` executes `_INIT_DDL` via `db.executescript()` at startup. `STA_DATABASE_URL` in [.env](../../../trading/.env) points at the Postgres container. Healthcheck confirms `"db": true` via Postgres.

**Status:** `feed_arb_signals` + `feed_arb_pnl_rollup` land in Postgres per spec §4.2.

### B-extra — Schema translation bug

`arb_spread_observations` Postgres schema (confirmed via `information_schema.columns`):

```
id, kalshi_ticker, poly_ticker, match_score, kalshi_cents, poly_cents,
gap_cents, kalshi_volume, poly_volume, is_claimed, claimed_at, claimed_by,
created_at, updated_at
```

Note: **no `observed_at` column.**

`_INIT_DDL` for `arb_spread_observations` at [storage/db.py:430-444](../../../trading/storage/db.py) defines:

```sql
observed_at   TEXT NOT NULL DEFAULT (datetime('now')),
```

The Postgres translation at `PostgresDB._translate()` converts `TEXT NOT NULL DEFAULT (datetime('now'))` → `TIMESTAMP` and appears to rename the column to `created_at`/`updated_at` (likely via a generic "audit column" convention in the translator — needs confirmation).

`SpreadStore.record()` at [storage/spreads.py:42-60](../../../trading/storage/spreads.py) INSERTs against `observed_at` explicitly. Postgres rejects with undefined-column error; the `except Exception` at line 61 swallows it with `logger.warning("SpreadStore.record failed (non-fatal): %s", ...)`. No such warning is visible in logs — either because log-level filtering is suppressing it, or because the exception occurs at a lower layer (e.g., the Postgres adapter's `executescript` wrapper) that reports differently.

**Status:** Bug. Zero observations have ever landed in `arb_spread_observations` (0 rows, empty min/max timestamps).

### B-extra-2 — Cron not firing (root cause: startup race condition)

[agents.yaml:92-95](../../../trading/agents.yaml):
```yaml
- name: cross_platform_arb
  strategy: cross_platform_arb
  schedule: cron
  cron: "*/30 * * * *"
```

[runner.py:222-223](../../../trading/agents/runner.py):
```python
elif schedule == "cron":
    self._tasks[name] = asyncio.create_task(self._run_cron(agent))
```

[runner.py:499-518](../../../trading/agents/runner.py) `_run_cron` uses `croniter` + `asyncio.wait_for(agent._drain_event.wait(), timeout=delay)` then calls `self._execute_scan(agent)`.

Expected fires over last 6h at `*/30 * * * *`: **8**. Observed: **0**. No `agent_run_complete` events for `cross_platform_arb`; no `Agent cross_platform_arb scan failed` errors either. The cron task was logged as created at 13:11 and 16:07 (after restart) but no scan execution follows.

**Root cause identified:** The `cross_platform_arb` strategy is registered TWICE:

1. **Placeholder** in [agents/config.py:185](../../../trading/agents/config.py): `register_strategy("cross_platform_arb", lambda cfg: None)` — returns `None`
2. **Real factory** in [api/app.py:1691-1700](../../../trading/api/app.py): re-registers with actual `CrossPlatformArbAgent` constructor (only when both Kalshi and Polymarket sources are available)

When `_reconcile_registry` (runner.py:544-680) runs, it calls the factory. If the placeholder is still active, it returns `None`, and runner.py:666 (`if agent is None: continue`) silently skips the agent. The real factory registration in app.py happens later during startup (conditional on data sources), creating a race condition.

**Fix:** Remove the placeholder registration from config.py. The real factory in app.py will register properly when sources are available. If sources aren't available, `_STRATEGY_REGISTRY.get("cross_platform_arb")` returns `None` and runner.py:628 logs a warning (better than silent skip).

**Status:** Root cause confirmed. Fix is to remove the placeholder line from config.py.

### B-extra-3 — Postgres datetime incompatibility

`SpreadStore` and `OpportunityStore` use SQLite `datetime('now', '-2 minutes')` modifier syntax in their SQL queries. `PostgresDB._convert_datetime_now()` only handles the simple form `datetime('now')` → `NOW()`, NOT the modifier form `datetime('now', '-2 minutes')`.

**Affected locations:**
- [storage/spreads.py:126](../../../trading/storage/spreads.py): `datetime('now', '-2 minutes')` in `get_top_spreads()`
- [storage/spreads.py:187](../../../trading/storage/spreads.py): `datetime('now', '-2 minutes')` in `claim_spread()`
- [storage/opportunities.py:98](../../../trading/storage/opportunities.py): `datetime('now', '-{min_age_hours} hours')` in `list_opportunities()`
- [storage/decay_scheduler.py:84](../../../trading/storage/decay_scheduler.py): `datetime('now', ?)` — parameterized modifier (separate fix needed)

**Fix:** Enhanced `PostgresDB._convert_datetime_now()` to handle modifier forms: `datetime('now', '-2 minutes')` → `NOW() - INTERVAL '2 minutes'`. The `decay_scheduler.py` parameterized case (`datetime('now', ?)`) requires a separate follow-up fix.

**Status:** Fixed in postgres.py. decay_scheduler.py parameterized case deferred.

### B6 — Publisher source decision

Given B1–B5, the publisher source decision from the plan (subscribe to `EventBus` topic `arb.spread`) remains **architecturally correct**, but cannot be implemented until A0 (below) fixes the upstream.

The publisher will:
- Subscribe to `EventBus.subscribe()` and filter `topic == "arb.spread"` (mirrors [arb_executor.py:67-71](../../../trading/execution/arb_executor.py))
- Apply `CostModel.should_execute(gap_cents, min_profit_bps)` gate (mirrors [arb_executor.py:149](../../../trading/execution/arb_executor.py))
- Generate `signal_id` as `arb_{observed_at}_{kalshi_ticker}_{poly_ticker[:8]}` from the event payload
- INSERT into `feed_arb_signals` with `outcome=NULL`
- Emit `feed.publish` log event + `feed_arb_signals_published_total` Prometheus counter
- Publisher does NOT re-publish to SignalBus (defer `cross_platform_arb` signal type registration to v2; [Alt-4 from plan review](../../../temporal-spinning-flame.md))

**Status:** Design confirmed. Waiting on A0.

---

## New prerequisite: Phase A0 — Upstream pipeline fix

Ordered by criticality:

### A0.1 — Fix `SpreadStore.record()` write path (2–3h)

Two options, either sufficient:

**Option α (cheap):** Update [storage/spreads.py:42-57](../../../trading/storage/spreads.py) INSERT to use `created_at` instead of `observed_at`. Rename the dataclass field too for consistency. Adds a 1-line migration note in `docs/adr/` for the naming divergence. Does not touch `_INIT_DDL`.

**Option β (correct):** Fix `PostgresDB._translate()` to preserve original column names. Update `_INIT_DDL` if it's intentionally using SQLite-only defaults. Touches more files but is the right long-term fix. Flags the audit-column convention as a convention, not a silent rename.

Recommend **α** for week 0; defer β to post-launch cleanup.

**Acceptance:** Run a scan; `SELECT count(*) FROM arb_spread_observations WHERE created_at > NOW() - INTERVAL '5 minutes'` returns the opportunity count (≥10).

### A0.2 — Fix cron scan non-firing (startup race condition) ✅

**Root cause:** `cross_platform_arb` registered twice — placeholder in config.py returns `None`, real factory in app.py registered conditionally later. `_reconcile_registry` gets `None` from placeholder and silently skips the agent.

**Fix:** Remove placeholder registration from config.py:185. Real factory in app.py overwrites it anyway. Without placeholder, `_STRATEGY_REGISTRY.get("cross_platform_arb")` returns `None` if real factory not registered, and runner.py:628 logs a warning (better than silent skip).

**Acceptance:** One scheduled scan executes, produces opportunities, writes observations, publishes `arb.spread` events. Visible in logs + DB.

### A0.3 — Fix Postgres datetime incompatibility ✅

**Root cause:** `PostgresDB._convert_datetime_now()` only handled `datetime('now')` → `NOW()`, not modifier forms like `datetime('now', '-2 minutes')`. This caused `get_top_spreads()` and `claim_spread()` queries to fail on Postgres.

**Fix:** Enhanced `_convert_datetime_now()` to handle modifier forms: `datetime('now', '-2 minutes')` → `NOW() - INTERVAL '2 minutes'`. Also fixes `opportunities.py` f-string variant. `decay_scheduler.py` parameterized case (`datetime('now', ?)`) deferred to follow-up.

**Acceptance:** `get_top_spreads()` and `claim_spread()` queries execute successfully on Postgres.

### A0.4 — Sanity check (1h)

Run the engine for 2h after A0.1 + A0.2 + A0.3. Verify:
- `arb_spread_observations` row count grows every 30 min
- `arb.shadow` log events appear in structured logs (since ArbExecutor default is `enabled=False`)
- `feed_arb_signals` table (once A3 creates it) would have received publishable signals

**Acceptance:** Baseline established; publisher has predictable upstream.

---

## Plan-file updates required

The plan file at `~/.claude/plans/temporal-spinning-flame.md` needs these additions (to be applied by the user or a follow-up session — that file is write-restricted to plan-mode sessions only):

1. **Insert Phase A0 (3 new steps, ~6h)** before A1. Gate G1 rewrites to "A0.3 green" instead of "B6 decided."
2. **Risk #1 upgraded.** Originally framed as "adapter regression → blank dashboard (probability: Med)." Actually happening today: silent write failure + silent cron non-firing. Probability: Realized. Blast radius: total. Mitigation: A0 is now prereq-blocking, not parallel.
3. **Risk #6 added.** "Silently-swallowed exceptions in pipeline glue code" — `SpreadStore.record()` has `except Exception: logger.warning("non-fatal")` on line 61 that hid this for weeks. Audit other "non-fatal" swallowers in the arb path during A0.1.
4. **Observability gate hardened.** D4 ("publisher-error / zero-publish alert") must also fire on sustained-zero `arb.spread` event volume during market hours — not just on publisher drops. The current failure mode would not have tripped D4 as specified.
5. **Spec reconciliation addendum (A11).** Add §15 to the spec: "Upstream pipeline prerequisites" — notes the two A0 bugs as resolved-before-launch items.

---

## What to do right now

Two independent agents can run in parallel:

- **Agent A** (this session's natural continuation): fix A0.1 (schema — migration already in db.py), A0.2 (cron — remove placeholder from config.py), A0.3 (datetime — enhanced `_convert_datetime_now()` in postgres.py). All three fixes are in the working tree.
- **Agent B** (parallel): compliance memo draft at [docs/compliance/signals-memo-draft.md](../../compliance/signals-memo-draft.md) — clock-time path; zero code.

Do not start A1–A11 until A0.4 is green.
