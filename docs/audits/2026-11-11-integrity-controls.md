# Integrity and execution controls: first implementation batch

Scope: local changes following the November 11 audit. No live trading, deployment,
production migration, remote API invocation, or broker operation was performed.
All behavior checks use copied source, temporary databases, mocked services, and
an outbound-network guard. Existing working-tree changes are preserved.

## Memory behavior

Local SQLite deduplication now includes agent identity, visibility, and visibility
scope. Identical private content owned by two agents creates two records. A
repeated write returns the actual stored record without renewing its expiry or
reviving a deleted or otherwise inactive memory.

TTL accepts positive integer durations with s, m, h, d, or w units. Ordinary
search/list retrieval excludes expired records and all statuses except active
and confirmed. Exact tag filters apply before limiting results. Omitting an
agent selects the legacy unowned namespace; cross-agent public retrieval must
explicitly request public visibility. Trusted history inspection may use
include_inactive. Low-level ID-based get/delete/status methods remain trusted
storage primitives, not authorization boundaries.

The schema initialization transaction replaces the global content-hash index
with a scoped unique index and adds absent legacy columns. Existing rows are
retained. Migration was tested on temporary SQLite stores only. Existing null
hashes are not backfilled, and ownership lost to historical global deduplication
cannot be reconstructed automatically. Unexpected incompatible data causes
initialization to fail rather than deleting records. Do not roll back to code
that recreates the global index after writing duplicate content across owners.

The hybrid client now requires an agent identity for local fallback, preserves
TTL, and reads only that agent's records plus explicit public commons. Remote
health distinguishes an outage from an empty result. The application still
needs deliberate hybrid-client wiring and API/SDK contract repair in a later
batch; these changes do not claim the full memory UI works end to end.

Memory linting distinguishes elapsed expiry from a future expiry and distinguishes
zero accesses from explicitly missing provenance. Prompt context generation now
imports the asyncio helper it actually uses.

## Trading controls and recovery

The risk engine uses its KillSwitch as the local halt state and synchronizes with
Redis. Initialization restores persisted control state before the strategy router
is initialized. Control-store initialization failure blocks that engine. A failed
halt or resume write keeps local execution blocked; successful explicit recovery
is required after a persistence fault. Missing risk configuration cannot be
cleared through the resume operation.

Halt and state-refresh operations share a per-engine lock. Halt attempts cancel
open orders on registered brokers and return cancellation failures; each broker
cancellation has a ten-second timeout. Two-step tokens are consumed atomically
with Redis GETDEL. Scope checks precede control checks on affected routes.
Authenticated single-order cancellation remains available while halted or while
Redis is unavailable.

This is not a distributed submission barrier. An order already past a check can
still race a halt, and a halt that cannot be persisted cannot be guaranteed to
reach another process. Direct order placement/modification and independent
execution workers still need a common submission boundary with complete risk
context. Existing standalone risk engines without a bound store remain usable
for isolated tests. These limitations prohibit a live-readiness claim.

Paper startup inserts the PAPER account only when absent. It no longer resets
persisted balances, and restart regressions preserve positions and order history.

## Studio result integrity

The random-walk simulator remains available as a demonstration. Results now state
synthetic_random_walk provenance, strategy_evaluated=false,
deployment_eligible=false, and fees_included=false. Equity uses post-fill cash
plus holdings; win rate counts profitable closed trades instead of sells.

Both the UI and deployment handler reject synthetic or unverified results,
including old results labeled real. No genuine historical-strategy validation
pipeline was added. Provenance flags are a guard against the existing misleading
simulation, not a substitute for an independently verified evaluation artifact.

## Next implementation boundary

Preserve the broker interfaces, paper ledger, risk rules, local store, prompt
store, and schema tooling. Next, consolidate all order submissions and amendments
behind one execution service, with trustworthy portfolio/daily-risk inputs and
rechecked halt state. Then repair memory API/SDK/MCP wiring and verify a complete
local user flow. Live trading and deployment remain outside the authorized scope.

## Verification

- Final broad unit run: 2,882 passed, 2 failed, 2 integration-marked tests deselected.
  The two failures reproduce the audit baseline: external sentiment retrieval in
  test_alphavantage_sentiment and the date-sensitive multiple-windows confidence
  calibration fixture.
- The two meta-learner test files run in separate processes to avoid the native
  XGBoost crash observed in the audit: 10 and 8 passed. Total unit passes across
  these partitions: 2,900. This is not a clean single-process suite pass.
- Final focused checks: 252 passed, overlapping the broad suite.
- Startup integration selection: 2 passed.
- Frontend production build passed. Frontend tests: 31 passed, 3 existing
  localStorage failures. TypeScript: the same 57 diagnostic messages as the audit
  after ignoring line-number shifts.
- Undefined-name checks passed for the changed core modules and regression file;
  git diff whitespace checks passed. No comprehensive dependency/security scan or
  production qualification was performed.

Detailed receipts and the sandbox runner are saved at
/Users/mspeicher/agent-memory-artifacts/integrity-20261111/.
The runner uses the existing backend virtual environment and frontend locked
installation from the audit sandbox, not newly installed backend dependencies.

## Subsequent execution work

The next batch is recorded in [Shared execution boundary](2026-11-11-execution-boundary.md).
It supersedes the direct-submission limitations above and changes missing control
state to start halted. Other limitations remain as documented there.
