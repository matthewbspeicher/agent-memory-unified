# Storage initialization and readiness

Status: implementation authorized by Matthew's instruction to use the recommended
answers to the remaining questions while he is away. Base: `58d12e1`.

## Agreed scope

Keep Claude's bootstrap fixes, existing schema, table owners, automatic fixups,
account seeding and all data. No new migration or DDL, no account resets, dependency
changes or configuration renames. Required unusable storage fails startup after
cleanup. Optional initialization failures remain observable without blocking usable
core storage. Preserve `/ready`'s existing response shape and unmanaged lightweight
application behavior.

Required storage covers Opportunity and trade tracking; configured paper operation
also requires its ledger, dispatch evidence, risk records and supported transactional
handles. Reconciliation and matching requirements follow enabled runtime paths,
including worker-mode exclusions. Existing lazy exit-handoff provisioning stays lazy.
Readiness is a read-only structure/read check, not proof of write permissions, order
admission, risk eligibility, consumer health or live-trading readiness.

## Interface choice

Considered: (1) explicit owned session, (2) extensible store callback/dependency
registry, (3) automatic lifespan adapter. Choose the explicit session plus a narrow
application cleanup wrapper. A registry adds construction and dependency machinery;
a fully automatic final gate hides ordering after execution producers start.

`StorageSession(config)` retains `DatabaseConnection` through an async context.
`certify(paper_store=..., position_store=...)` binds actual store handles and checks
the final required structure after existing owners initialize it. `check()` repeats
bounded read-only checks. Pending/closed sessions fail; transient failures can recover.
The existing raw database handle remains the persistence interface.

Initialization helpers retain their legacy return contracts and SQL. An optional
typed collector records unexpected failures by step/error type; expected duplicate
columns are not failures. Warnings record attempted initialization, not final usability.

The application retains sessions in an exit stack at the existing acquisition point.
A wrapper runs existing dependent cleanup on startup/serving failure and normal exit,
attempts remaining cleanup after individual failures, and closes shared storage last.
The required gate follows paper initialization and precedes agent runtime setup.

`/ready` delegates only the managed database decision; Redis and broker checks keep
their existing meanings. Missing or substituted managed handles fail closed.

## Verification

Baseline: 33 focused connection, health and paper-startup tests passed on the base.
Add lifecycle failure/cancellation/cleanup and managed health contract tests; test
session certification with real SQLite/PostgreSQL, including preserved account
balances, Opportunity revisions and Account generations, read-only repeated probes,
missing required schema, matching flags and worker mode. Exercise existing complete
paper CI selection with disposable PostgreSQL and real Redis, including its failure
control; run the required unit/storage suite. Review final source and exact receipts.

No live trading, deployments or skill publishing. Prepare a reviewable PR; do not
merge this new change without a later review/merge request.
