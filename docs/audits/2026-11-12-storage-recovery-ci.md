# Storage and paper recovery in CI

Base: `bcde30e63fb32355960bd1296f1b71593815192f`, the merge of PR #8.
PR #8 was independently reviewed against the repository standards and the
starting-balance requirements; neither review found a supported blocker. Its
exact head `e084623e9845bdc5f008126b94b00d9d04cf977b` had passing local unit,
storage and paper integration qualification and terminal GitHub CI before merge.

## CI changes

The existing `trading-tests` job now runs `tests/unit` and `tests/storage`, with a
30-second per-test timeout. OMP, OpenBLAS and MKL thread counts are bounded to one,
matching local native-ML qualification. The frontend build and existing non-fatal
mypy policy are unchanged.

A separate `paper-recovery-tests` job runs the nine qualified paper lifecycle
files against SQLite, PostgreSQL 17 and Redis 7.4.8. GitHub manages the disposable
service-container lifecycle. Runner-host clients reach the mapped service ports
through `127.0.0.1`; service credentials are test-only literals, not application
secrets. Health checks precede job steps. The job has a 15-minute timeout and
pytest has a 30-second per-test timeout.

The explicit file list covers configured starting balances, durable dispatch and
lost responses, PostgreSQL execution, resting orders, partial fills and their
reconciliation, entry-to-exit cancellation, cumulative exposure, partial-fill
commissions, and automatic matching/expiry. It deliberately excludes the other
integration files, some of which require provider connections. Add future paper
cases to this qualified selection rather than broadening the job to all
integration tests without checking their dependencies.

The recovery command clears pytest.ini's default `addopts` integration exclusion,
then selects `integration and not live_paper`. It uses only the fixtures'
`AMU_TEST_POSTGRES_DSN` and `AMU_TEST_REDIS_URL`; it does not configure an
application database, start the trading engine or load broker credentials.
Missing services or failures fail the job. No test step uses `continue-on-error`
or suppresses pytest's status.

## Storage fixture correction exposed by CI

The first GitHub run passed all 237 recovery cases, but failed five newly selected
storage cases at `await connection.execute(...)`. Their spec-derived connection
mocks supplied a non-awaitable `MagicMock` on Python 3.12.16. The local Python
3.13.12 mock supplied an `AsyncMock`; both environments used aiosqlite 0.22.1.
The real connection path passed in both environments.

The affected SQLite connection tests now use disposable in-memory connections
rather than inferring an awaitable interface from a mock spec. Original connection,
row-factory, initialization and store-injection checks remain; the tests additionally
exercise row access and failure to execute after context-manager closure. No test
was removed or skipped, and no production connection code or dependency changed.
All 20 storage cases pass locally after this correction. The first failing CI
receipt is retained with the qualification artifacts.

## Local qualification

Validation read the pytest commands directly from the changed workflow. It used
the existing local Python 3.13.12 environment; GitHub's clean Python 3.12 run is
the authority for the hosted-runner/dependency combination.

- Recovery command: **237 passed**, with actual disposable PostgreSQL and Redis
  services and temporary SQLite files.
- Backend command: **3,214 unit/storage tests passed, 3 default-marker
  deselections**, with 9 existing `datetime.utcnow()` deprecation warnings. No
  native ML test files were excluded.
- Collection receipt: 237 selected items, all marked `integration`, none marked
  `live_paper`, including both SQLite and PostgreSQL parametrizations.
- Failure control: an opt-in QA-only pytest hook failed one selected recovery
  case; the same workflow command returned **exit 1** with the intentional
  failure. No repository test was changed or skipped for this control.
- Test containers and anonymous volumes were removed after validation.

Logs, collection metadata, command/exit receipts and the PR #8 merge receipt are
under `/Users/mspeicher/agent-memory-artifacts/ci-storage-recovery-20261112/`.
The collection/failure probe and local Docker runner are outside the repository
and are not part of CI.

The existing schema-generation commit hook requires the unavailable local
`datamodel-codegen` tool. It is bypassed for this workflow/docs-only commit;
no schema inputs, generated types, dependencies or persistent hook settings change.

No production code, dependency declarations, database schemas, provider adapters,
deployments or marketplace artifacts are changed by this CI update.

## Documentation checked

Current Context7 lookups used the official
[GitHub service-container documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idservices)
and [pytest command-line configuration documentation](https://github.com/pytest-dev/pytest/blob/main/doc/en/reference/reference.rst).
