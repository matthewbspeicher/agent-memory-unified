# UTC sessions for the engine's PostgreSQL pool

## Request

Pin PostgreSQL sessions to UTC so timestamp defaults agree with stored UTC
values. Preserve existing behavior and data; keep tests paper-only. No live
trading, deployments or skill publication.

## Change and scope

`DatabaseConnection.connect()` passes `server_settings={"TimeZone": "UTC"}`
to `asyncpg.create_pool`. This sets UTC when each physical engine connection
starts, including connections created after pool expiry or reconnection. The
native pool's normal reset restores that startup setting before reuse. No
per-query timezone command or custom reset callback is added.

SSL configuration and `statement_cache_size=0` are unchanged. Other DSN/role
settings, including search path and application name, remain effective.

Only the shared engine connection manager changes. Existing rows, balances,
orders and timestamps are not rewritten, and database/role defaults are not
altered by application code. Existing running pools are not reconfigured by
this source change; the policy takes effect when a pool connects. Independent
maintenance/diagnostic scripts and the standalone embedding consumer keep their
separate connection paths; they are not the normal trading-engine pool.

## Verification

Before the change, all eight new integration cases failed: engine sessions
inherited either the role's Asia/Tokyo setting or a conflicting Pacific/Honolulu
DSN setting.

The tests exercise the actual `DatabaseConnection.connect()` path and real
asyncpg pool against a disposable PostgreSQL role/schema, with two baseline
configurations. They verify:

- Two simultaneously borrowed sessions use UTC and retain unrelated settings.
- TIMESTAMP/CURRENT_TIMESTAMP and DATE/CURRENT_DATE defaults agree with UTC
  TIMESTAMPTZ instants and explicitly bound UTC values.
- A borrower's timezone change cannot leak past release/reset, including an
  explicit `RESET ALL`.
- Expired physical connections are replaced with new UTC sessions, and the
  facade's pinned transactions see UTC as well.
- Closing/reopening the manager preserves UTC policy without changing the
  role's own non-UTC default or a seeded legacy timestamp row.

Only the known, separately documented schema-bootstrap step is replaced in
these connection-policy tests. Pool creation, reset, replacement, facade and
transactions are real; these tests do not claim to fix the bootstrap DDL issue
or validate an external connection pooler. All roles, schemas and service
containers are disposable. No real application database is contacted.

The new file is added to CI's explicit paper integration allowlist alongside
existing SQLite/PostgreSQL execution, recovery, fill, approval and gate tests.
Connection unit tests retain their SSL/SQLite coverage and check that the UTC
setting and disabled statement cache are passed together.

Reference: [asyncpg connection configuration](https://magicstack.github.io/asyncpg/current/api/index.html#asyncpg.connect)
and [pool configuration](https://magicstack.github.io/asyncpg/current/api/index.html#asyncpg.create_pool).
The configuration/reset behavior was also checked against the installed
asyncpg 0.31.0 source and real pool lifecycle tests.

Local terminal receipts: 13 focused connection tests, 3,328 unit/storage tests,
and 397 paper integration tests passed. The integration collection failure
control exited 1 as intended, and disposable PostgreSQL/Redis containers were
removed. Receipts are retained outside the checkout under
`/Users/mspeicher/agent-memory-artifacts/postgres-utc-sessions-20261112/`.
