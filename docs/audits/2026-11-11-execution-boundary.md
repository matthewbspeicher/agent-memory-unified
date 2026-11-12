# Shared execution boundary

Local implementation following the integrity audit. No live trading, deployment,
external broker operation, or migration of a real database was performed.

## Admission and preservation

`execution/service.py` now owns application submission and amendment transport.
HTTP orders, strategy execution, WhatsApp confirmation, arbitrage legs and
arbitrage unwinds all use it. Cancellation remains outside admission. A source
architecture test prevents new application calls to raw broker placement or
amendment methods. Broker adapters remain transport implementations, not independently
safe public entry points.

Each attempt validates canonical order terms, registered broker/account identity,
fresh quotes, complete measured portfolio state, daily P&L and trade counts, all
configured risk rules, and the persisted halt immediately before transport.
Amendments require a durable original order and a matching authoritative open-order
snapshot; only quantity, limit price and stop price can change. Filled quantity is
excluded from the replacement risk calculation. Risk-approved size reductions are
sent to the broker. Earlier constraints are rechecked after sizing changes, since
shrinking an offsetting order can increase projected exposure. Empty policies, unavailable inputs and unsupported order types
are refused. Advisory strategy previews never replace final admission.

A shared Redis NX lock serializes admission across workers. Pending reservations
survive service recreation and prevent concurrent split orders from manufacturing
capacity. The lock has no expiry: timeouts, cancellation after dispatch, invalid
receipts and persistence failures retain the lock rather than permit an unsafe
retry. Attempts record full order terms before transport and receipt identity after
acknowledgement. Strategy outcomes with an ambiguous transport result are marked
`reconciliation_required`, not definitively rejected. Missing control state starts
halted; a configured halt overrides a persisted resume.

Existing broker interfaces, risk rules, strategy flow, paper ledgers and confirmation
flow remain. Position limits now account for projected long and short holdings;
missing daily measurements cannot silently become zero. WhatsApp consumes its
confirmation token before execution and reports persistence/cancellation failures.
Arbitrage acknowledgement is no longer treated as a fill. Startup uses one
coordinator, registers late-added brokers before its worker starts, and supplies
paper accounts to the automatic executor. Manual arbitrage selects paper brokers
and observed-price limit orders without a live fallback. WhatsApp receives the
resolved primary account.

## Paper evidence

SQLite paper accounts now record risk events and coverage generations. Risk state
includes marked equity, current-day fills and realized P&L net of fees, plus negative
unrealized P&L as a conservative loss allowance. This is not midnight-to-midnight
mark-to-market performance. Missing legacy coverage blocks admission rather than
inventing history. A reset creates a new generation so old reservations cannot be
mistaken for current holdings.

File-backed ledgers use a dedicated connection and owned transactions for cash,
positions, orders and risk events. They cannot commit another subsystem's pending
work. Snapshots detect changes while marks are obtained. Prediction and stock paper
fills require real supplied quotes; unmarketable limits and untriggered stops are
rejected instead of fabricated fills. Only temporary databases were initialized in
verification. New risk-event/coverage tables require normal schema initialization
before this code can be used with an existing local ledger.

## Reconciliation procedure and limits

The service's `reconciliation_status()` is read-only. It returns the held lock,
last attempted order and persisted reservations. There is intentionally no automatic
unlock or retry endpoint.

1. Halt and quiesce every execution worker before investigating a retained lock.
2. Preserve the lock, attempt and reservation records. Match the attempt token to
   the lock; an older acknowledged attempt does not establish the new lock's outcome.
3. Reconcile the actual venue/ledger using account, full order terms, timestamps,
   order IDs, fills and open orders. A timeout or missing response is not proof of
   rejection. If identity or outcome cannot be established, leave admission blocked.
4. A separately reviewed recovery must persist the reconciled reservation/terminal
   state before releasing the matching lock. Restarting or deleting the key blindly
   is not recovery. No such operational recovery was performed in this task.

This is local qualification, not live readiness:

- SQLite paper accounts provide the complete contract. Live adapters and PostgreSQL
  paper storage do not, so order admission rejects them. Unsupported paper storage
  keeps startup available with an explicit warning. Compose's PostgreSQL configuration
  therefore cannot paper trade through this boundary yet.
- Combo/bracket orders and amendments to unknown or externally changed orders are
  refused. Paper fills are immediate or rejected; a resting-order simulator was not
  added. Prediction unwinds that still request unsupported market orders fail closed.
- Some strategies still specify legacy live broker/account aliases. Those calls are
  blocked by account/provider validation, not silently redirected. Router preliminary
  sizing and account selection need a separate cleanup; final admission is authoritative.
- Existing `MaxPortfolioExposure` remains a per-order percentage rule. This batch does
  not turn it into an aggregate gross-exposure policy or add missing sector/history
  providers. Configured sector/correlation rules require their context or admission
  is refused.
- Halts block all submissions, including unwinds; cancellation remains available.
  Reliable multi-broker cancellation and reduce-only policy need further qualification.
- The final halt guard serializes local control changes with transport. It cannot
  retract a request already issued by another process. Broker-side fencing, automatic
  recovery of interrupted arbitrage, and readiness reporting are not implemented.
- Redis durability and eviction policy are deployment requirements, not proven here.
  Loss of all reservation/control state requires reconciliation, not an ordinary resume.

## Verification

Tests use a copied source tree, sanitized environment, temporary databases and an
outbound socket guard. No frontend code changed in this second batch.

- Final broad unit run: 3,002 passed, two known baseline failures, two startup tests
  deselected for separate execution (55.74 seconds).
- The two native ML suites ran in separate processes: 10 and eight passed. Running
  both in one process previously produced a native XGBoost crash; this is a test
  environment limitation, not evidence that combined-process execution is safe.
- Startup integration: two passed. Real SQLite paper arbitrage integration: two passed.
- Total across those disjoint partitions: 3,024 passed, two baseline failures.
- Final focused risk/boundary/router run: 162 passed (included in the unit total).
- Undefined-name lint and git whitespace checks passed.

Baseline failures remain unchanged: `test_alpha_vantage_sentiment` attempts an
external Fear & Greed feed blocked by the network guard; calibration
`test_multiple_windows` uses March dates outside the current 30-day window. Neither
was hidden, skipped or repaired as part of execution work.

A fresh Claude Code session, **Agent-memory-unified execution-risk review**, supplied
an independent read-only review. Its report contains observations from multiple
intermediate revisions, including superseded findings; it is review evidence, not
an assertion that all remaining capabilities work. Confirmed gaps and the implemented
fixes are distinguished above.

Receipts, review and isolated runner:
`/Users/mspeicher/agent-memory-artifacts/execution-20261111/`.
The backend virtual environment was reused; no dependency upgrades were made.

## Subsequent PostgreSQL work

[PostgreSQL paper execution](2026-11-11-postgres-paper-execution.md) supersedes the
PostgreSQL paper-storage limitation above. SQLite and PostgreSQL now implement the
same paper risk contract; live adapters and the other listed limitations remain.

## Subsequent recovery work

[Execution recovery](2026-11-11-execution-recovery.md) now provides explicit, halted
recovery for identified dispatch outcomes, including open/partial reservations.
Its durable-dispatch section supersedes the earlier manual-only recovery limitation.
