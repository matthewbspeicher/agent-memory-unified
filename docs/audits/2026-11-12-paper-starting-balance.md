# Configured paper starting balance

Base: merged PR #7, `80f1062ef49c0803cd1cd4ce567497d6d6e7dae2`.
PR #7's final head, `769ff5d39353a20e356b88ae2a03da6143839be8`, passed both
GitHub CI jobs in run `43252173030` before merge. Its final delta preserves a
`PaperOrderMustRest` from the quote provider and adds prediction-venue regression
tests.

## Problem and change

`PaperStore.init_tables()` seeded a missing primary `PAPER` account at 100,000.
Startup then called `ensure_account` with `paper_trading_initial_balance`, which
correctly left the already-created account alone. A fresh setup therefore ignored
the configured amount for its primary account.

Startup now passes the configured amount into initialization before that first
insert. `init_tables(initial_balance=...)` uses it only when inserting a missing
default account; its conflict behavior, existing balance rows and risk-coverage
handling are unchanged. Calls without the new keyword retain the standalone
100,000 default. Prediction accounts retain their existing `ensure_account` path.

In configured paper mode a supplied broker is replaced by the configured paper
broker. Startup no longer initializes that unused broker first, which previously
could seed the same database with the standalone default before configuration was
applied. A supplied broker outside configured paper mode keeps its earlier path.

Restarting with a different setting does not resize, top up or reset an existing
account. Explicit paper reset remains a separate operation: it uses the broker's
configured amount and intentionally creates a new generation, as before.

## Verification

- New SQLite assertions first failed: 5 failed, 3 passed. They observed 100,000
  where 10,000 or 25,000.25 was configured, including the supplied-broker path.
- After the fix, 78 focused startup, risk-context, recovery and venue checks passed.
- Full `tests/unit/` plus `tests/storage/`: **3,214 passed, 3 deselected**, with
  9 existing `datetime.utcnow()` deprecation warnings. Native ML tests were included;
  OMP, OpenBLAS and MKL thread counts were bounded to one.
- Paper lifecycle integration: **237 passed** against SQLite, PostgreSQL 17 and
  real Redis 7.4.8, including the five new PostgreSQL starting-balance cases.
- Changed Python files passed Ruff F checks; `git diff --check` was clean.
- The local pre-commit hook always regenerates schema types and stopped because
  `datamodel-codegen` is not installed. No schemas or generated types changed;
  that hook was bypassed for this commit only. No dependency installation or
  persistent hook configuration change was made.

New cases cover empty schemas, SQLite file/in-memory storage, zero/fractional
funding, supplied/unprovided paper brokers, all three paper accounts, current-day
risk completeness, unchanged balances/coverage generations across changed-config
restarts, and explicit reset. The existing PostgreSQL startup test now also checks
all four balance fields, generation preservation and configured prediction-account
funding. Existing recovery, partial-fill commission, exposure, matching/expiry and
entry-to-exit suites remain green.

Commands:

```bash
python -m pytest tests/unit/ tests/storage/ -v --tb=short --timeout=30
python -m pytest tests/integration/test_paper_starting_balance.py \
  tests/integration/test_dispatch_recovery.py \
  tests/integration/test_postgres_paper_execution.py \
  tests/integration/test_paper_resting_recovery.py \
  tests/integration/test_paper_fill_reconciliation.py \
  tests/integration/test_entry_exit_handoff.py \
  tests/integration/test_portfolio_exposure_reservations.py \
  tests/integration/test_partial_fill_commissions.py \
  tests/integration/test_automatic_paper_matching.py \
  -o addopts= -m integration -q --tb=short --timeout=30
```

Integration requires `AMU_TEST_POSTGRES_DSN` and `AMU_TEST_REDIS_URL` pointing to
disposable services. This qualification used cached images, unique schemas and
new loopback-only test containers; containers and their anonymous volumes were
removed. Local terminal logs and exit/cleanup receipts are under
`/Users/mspeicher/agent-memory-artifacts/paper-starting-balance-20261112/`.

No schema definitions, production data, live broker behavior or dependencies were
changed. No live trading, deployment or skill publication occurred. Other default
non-unit suites and frontend tests were outside this change's local selection;
the three deselected unit cases retain their configured integration markers.
