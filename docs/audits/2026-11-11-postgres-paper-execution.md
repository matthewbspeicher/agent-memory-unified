# PostgreSQL paper execution

PostgreSQL paper accounts now use the same ExecutionService and complete risk-state
contract as SQLite paper accounts. Live broker adapters remain blocked. This batch
used only a disposable local PostgreSQL 17 container and temporary SQLite stores;
no existing database, live trading process or deployment was changed.

## Transaction ownership

PostgresDB.transaction() acquires one pooled connection, opens an asyncpg transaction,
and yields a separate facade pinned to that connection. It commits on success and
rolls back on exceptions or cancellation. Ordinary root-facade calls retain their
previous autocommit behavior. A root commit cannot accidentally commit a paper fill.
The database connection manager can now recognize and close the PostgreSQL pool.

PaperStore binds the facade to its owning task for the duration of a transaction.
Cash, positions, order history and daily-risk events commit together. Nested paper
operations reuse their owner's transaction. Before any paper transaction or risk
snapshot, PostgreSQL takes transaction-scoped advisory lock 718302641, shared by all
paper accounts/stores/processes within that database. Lock waits time out after five
seconds; pool acquisition times out after ten seconds. Failures before the transaction
body are definite non-writes; later failures remain subject to the execution service's
conservative reconciliation handling.

Risk snapshots hold the same database lock while reading and marking positions.
READ COMMITTED statements begin after lock acquisition, so a waiting snapshot sees
the completed write. Existing revision checks, quote freshness, coverage generation,
daily-loss calculations and all admission/halt checks remain in force. No guessed
daily metrics or separate PostgreSQL risk-policy bypass was introduced.

The lock serializes all paper accounts for correctness. This favors simplicity over
throughput; slow market-data reads can delay other paper accounts. Advisory locks
coordinate application paper operations, not arbitrary external SQL writers. Direct
external ledger changes still require quiescence and reconciliation. Redis admission
persistence and unknown-outcome recovery requirements from the preceding execution
batch remain unchanged.

## Startup and compatibility

Normal PostgreSQL startup initializes both prediction accounts with coverage, just
as SQLite does. Existing account balances and generations are preserved. A legacy
account without complete daily evidence still waits for valid coverage rather than
assuming zero P&L or fills. Unknown storage backends continue to fail closed.
PostgreSQL schema initialization uses an idempotent ALTER inside its owned transaction
so a duplicate column cannot poison that transaction. No new tables, dependencies,
configuration variables, or live adapter capabilities were added in this batch.

Paper amendments remain unsupported by the immediate-fill simulator. Unknown-order
amendments and unsupported advanced order types still fail at the shared boundary.
The existing float-based ledger representation and conservative daily-loss policy
are unchanged; this work does not claim accounting-grade decimal storage.

## Verification

- Real PostgreSQL integration: 12 passed. Every test uses an independent schema and
  the normal init_db_postgres initializer before PaperStore initialization.
- Covered shared-boundary fills, restart/count limits, halt rejection, forced failure
  after fill, cancellation rollback, unrelated root commits, concurrent independent
  stores, snapshot/write serialization, startup account preservation, legacy coverage,
  fees, loss marks, reset generation, carry fees and idempotent binary settlement.
- Both Kalshi and Polymarket paper adapters execute through the actual risk service
  against PostgreSQL. Market data and Redis controls are deterministic test providers.
- Focused PostgreSQL adapter/SQLite paper/risk/startup regressions: 136 passed.
- Broad unit regression: 3,002 passed, two unchanged baseline failures, two startup
  checks deselected for separate execution (57.36 seconds).
- SQLite application startup integration: two passed.
- Baseline failures: the Alpha Vantage sentiment test also requests an external
  Fear & Greed feed blocked by the guard; calibration test_multiple_windows has
  March fixtures outside today's 30-day window. Neither was skipped or altered.
- The two native ML suites were excluded from this broad run because their shared
  process previously crashed in XGBoost. They were not rerun for this storage change.
- Undefined-name lint and whitespace checks passed. Test schemas were all dropped;
  the PostgreSQL 17.11 container and anonymous data volume were removed.

Saved report and receipts:
`/Users/mspeicher/agent-memory-artifacts/postgres-paper-20261111/`.

The isolated runner strips application configuration and disables dotenv loading.
Its socket guard allows only the disposable container's exact loopback address and
published port. It blocks all broker, external feed and other network connections.
The container is removed after testing. Existing dirty worktree changes are preserved.
