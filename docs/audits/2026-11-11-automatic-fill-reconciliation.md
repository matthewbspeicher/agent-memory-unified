# Automatic paper fill reconciliation

Implemented locally; no live trading, deployment, user-database migration, commit,
or push. Tests use disposable ledgers and sanitized application environments.

## Durable flow

The paper opportunity router now writes a reconciliation job before submitting
through the existing risk boundary. A dedicated signal identity on a copied order
links that job to the durable paper order even when the submission response is
lost. Existing opportunity data and the caller's original signal are not overwritten.
A repeated opportunity cannot dispatch a second order.

The normal non-worker paper application starts a managed reconciliation task, polling
once per second. It observes committed paper evidence; it never submits orders,
advances matching, resumes execution, or clears uncertain-dispatch locks. Explicit
paper ticks remain the matching mechanism. Reconciliation works while execution is
halted. Authoritative recovery rejection tombstones release nonaccepted jobs;
absence of an order alone does not.

Cumulative fill receipts are keyed by broker, account and order. Each atomic tracked
position update applies only the new quantity, notional and fees. Replay is a no-op;
regressing/conflicting evidence is rejected. Owned SQLite connections or bound
PostgreSQL transactions avoid committing unrelated work. Paper generation is checked
inside the tracked write and again before the final projection, preventing a reset
race from projecting stale inventory.

Tracked quantities are stored as decimal text, with remaining and exited quantities
and realized PnL. Partial entry fills update weighted entry price and cumulative fees.
Partial exits reduce remaining quantity, aggregate weighted exit price and fees, and
allocate entry fees to realized PnL. Only zero remaining quantity closes the position.
Cancelling an unfilled remainder preserves already-filled inventory.

Opportunity receipts and trade history update in place, together with durable job
completion. A stale worker cannot overwrite a newer cumulative projection. Immediate
paper fills retain their existing full-fill router hooks; cumulative position/rule
updates replace the old whole-position entry/exit calls. Immediate fees are recovered
from the dispatch receipt when legacy paper rows lack detailed fill fees.

## Exit protection

Rules attach once the first fill creates a position. Retries preserve configured
rules and existing trailing state instead of resetting defaults. Defaults retain the
initial protection plan rather than moving stops on every additional entry fill.
Prediction contract expiry is preserved in tracked positions and default rules.

Rule reconciliation reads current durable position status in an owned transaction:
closed positions lose rules, and stale entry workers cannot reattach them. A surviving
process hydrates missing rules from storage before evaluating a position. Pending
entry/exit jobs suppress overlapping exit orders; after an entry finishes or its
remainder is cancelled, the monitor sizes exits from remaining quantity. Partial
exit cancellation releases the pending flag but keeps rules on the remaining position.
Missing rule evidence or storage errors suppress automated exits for investigation.

Subsequent partial-entry cancellation handoff: see
`2026-11-11-partial-entry-exits.md`. It supersedes the pending-entry wait below
for the normal paper exit monitor.

## Boundaries

- This applies to newly registered paper opportunity orders. Legacy orders lacking
  a durable opportunity association, and direct/manual paper submissions outside
  the opportunity router, are not guessed into tracked strategy positions.
- Active entry orders must finish or have their remainder cancelled before the
  monitor emits an exit. This prevents a later entry fill from reopening a position
  after an exit. The reconciler does not automatically cancel entry remainders.
- Completed asynchronous fills update positions, opportunity receipts, trade history
  and exit protection. They do not replay every optional router achievement, learning,
  reflection or execution-quality hook. Those are not exactly-once event consumers.
- Existing journal/analytics DTOs still contain integer quantity fields; this change
  establishes fractional precision in tracked storage and execution/exit sizing,
  not a migration of every downstream reporting format.
- Trailing peaks remain the existing process-local runtime state; missing-rule
  hydration restores durable rules, not unpersisted price history.
- Paper money/price aggregates retain the prior floating-storage limitations. Fill
  terms, detailed amounts and tracked quantities use decimal text.
- Old-generation jobs stay pending for investigation after an account reset. No
  automatic deletion or reinterpretation of tracked history is performed.

## Validation

- **130 passed** on real Redis 7.4.8, disposable PostgreSQL 17 schemas and SQLite.
  Includes 30 new automatic projection cases and 100 existing dispatch/matching/
  recovery cases. New cases cover partial entry/exit/cancel, automatic polling,
  lost responses, concurrent workers, projection retry, immediate and partial fees,
  actual router integration, duplicate exits, recovery rejection, prediction expiry,
  generation reset before and during projection, and in-place trade history.
- Broad unit suite: **3,078 passed**, two unchanged baseline failures and two startup
  tests deselected for separate execution (56.60 seconds).
- Startup: **2 passed**, including managed reconciliation task wiring. SQLite paper
  arbitrage: **2 passed**. Disjoint total: **3,212 passed**, two baseline failures.
- Baseline failures remain the network-dependent Alpha Vantage sentiment test
  blocked by the socket guard and calibration fixture dates outside the current
  30-day window. The two native meta-learner suites remain excluded because of their
  previously reproduced combined-process crash; they were not rerun for this task.
- Undefined-name lint and git whitespace checks passed.
- Redis keys and temporary PostgreSQL schemas were confirmed empty after tests.
  Both disposable containers and volumes were removed.

The copied-source test runner used sanitized environment variables and blocked
outbound networking except the two exact local disposable service ports. Source
changes are local and uncommitted. No user application or database was migrated.

Receipts: `/Users/mspeicher/agent-memory-artifacts/fill-reconciliation-20261111/`.
