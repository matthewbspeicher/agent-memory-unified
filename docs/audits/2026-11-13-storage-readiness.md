# Storage initialization and readiness

## Result

The managed application retains its shared database owner through shutdown and
refuses startup when required initialized storage cannot be read. `/ready` checks
required storage structure on the actual store handles instead of relying on
`SELECT 1`. Its JSON shape and unmanaged lightweight-app behavior are unchanged.

`StorageSession` owns the connection, one certification step and bounded live
checks. `PaperStore` and `TrackedPositionStore` own their read-only inspections;
ledger table names remain inside the existing owner, enforced by the unchanged
architecture test. Enabled paper reconciliation/matching add their eager tables;
worker mode excludes consumers it does not start. Lazy exit-handoff table creation
remains lazy. Checks neither initialize schemas nor open admission transactions.

Unexpected initialization failures are retained as sanitized step/error-type
diagnostics. Existing duplicate-column retries are expected. A failed attempt is
not necessarily an unresolved failure: later existing fixups can repair it.
Timestamp-fixup messages keep their previous debug severity; their unchanged SQL
can still produce advisory type-mismatch diagnostics on text timestamp columns.

Startup failure, normal shutdown and cancellation attempt dependent cleanup before
shared database closure. Individual errors/cancellations do not skip later owners;
the original startup error is preserved. An unreturned PaperStore also closes its
dedicated SQLite handle when broker setup fails. PostgreSQL pool drain is bounded,
with termination fallback on drain failure.

## Data and behavior preservation

No DDL, migrations, account reset, account-seeding policy, balances, saved
Opportunity revisions, Account generations, order admission, outcome interpretation,
retry/recovery rules, dependencies or configuration names changed. AST comparison
found existing mutation/schema SQL literals unchanged in database initialization
(28), paper ledger (34) and tracking (19). New probes execute SELECT only.

## Verification

Initial base: `58d12e1f1c7eecec9507ef7ea6527d2a3cc6cdf2`.
Integrated main: `e509abe` (Claude's float decoder and PostgreSQL UTC session fixes).
The connection conflict was resolved by retaining lifecycle handling and the UTC
pool setting. The UTC fixture's bootstrap assertion now includes the diagnostics
collector; its behavior assertions remain unchanged.
Isolated checkout: `agent-memory-unified-worktrees/storage-readiness-design`.
The concurrent Claude checkout was left untouched.

- Baseline focused checks: 33 passed.
- Reproduced acquisition leak using the original database module: injected
  initialization failure left the acquired SQLite connection open (control exit 1).
  Same check after the fix released it (exit 0); the control cleaned its fixture.
- Complete combined local unit/storage suite: 3,503 passed, 1 existing skip and
  3 deselections.
- Complete combined paper CI selection: 469 passed with disposable PostgreSQL 17 and Redis
  7.4.8, including 26 new SQLite/PostgreSQL readiness cases. Failure control exited
  1 as required, and both disposable containers were removed.
- Source review: Standards 0 remaining findings; Spec 0 remaining findings. The
  cleanup-cancellation finding was corrected and covered by regression tests.
- Ruff and whitespace checks passed. Local mypy is unavailable; CI retains its
  established nonfatal mypy check.
- The local unconditional type-generation hook needs unavailable `datamodel-codegen`
  and `quicktype`. Commits use a single-command hook override; no JSON Schema,
  generated types or persistent hook configuration is changed.

The first broad checks caught an initialization-log severity regression and a
ledger-ownership violation. Both were corrected without weakening those tests.
The final passing runs follow the corrections.
The first hosted Python 3.12 backend run then found two test-mock protocol
differences: `execute` needed an explicit awaitable mock before the injected
failure. Those fixtures were corrected, and a missing session-binding type
annotation was added. The 60 focused checks and complete local backend suite
passed again; hosted validation is bound to the final PR head separately.

Task-local logs, collection receipts, failure control, SQL-preservation comparison
and before/after acquisition control are under
`/Users/mspeicher/agent-memory-artifacts/storage-readiness-design-20261113/`.
Combined-main terminal receipts are in its `combined-main/` directory.

## Limits

Readiness establishes structure/readability and supported transaction implementations;
it does not prove future write permission, every constraint/type/default, worker
health, per-account risk eligibility or whether an order is safe. Lifecycle tests
use controlled startup with real SQLite handles; they do not start the configured
application's external clients. Paper integration tests exercise real storage and
Redis using disposable fixtures. No live trading, deployment or skill publication.
