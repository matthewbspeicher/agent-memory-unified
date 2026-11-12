# Execution recovery: terminal acknowledgements

ExecutionService.recover_acknowledged(token) provides an explicit recovery operation
for a retained admission lock when a durable acknowledged receipt exists and fresh
account state independently confirms its order ID is terminal. It requires trading
to be halted and leaves that halt in place. No order is submitted or retried.

Recovery removes the reconciled reservation and records status=recovered and its UTC
time. Redis performs those writes and releases the matching lock in one Lua script.
The script compares the lock token, original attempt bytes, original journal bytes
and persisted halt. A concurrent resume or changed recovery input invalidates the
operation. An ambiguous Redis response must be investigated using reconciliation_status;
never assume the operation failed and retry an order.

This operation is an internal service method, not a new HTTP endpoint or automatic
startup action. Operators must quiesce all workers before using it. It does not recover
prepared-only attempts, open/partial outcomes or receipts without an authoritative
terminal ID. Those remain blocked. Complete recovery of a lost broker response needs
a durable dispatch identity and provider evidence that identifies the exact attempt;
matching order terms or an empty history is insufficient. That work remains outstanding.

Verification: 155 focused execution/caller/risk tests passed, including six new
recovery cases. Covered successful recovery, preserved halt, concurrent state change,
missing terminal evidence, control-store failure and prepared-only refusal. Atomic
Redis behavior is represented by a test double; the Lua script has not yet been
qualified against a real Redis server. Undefined-name lint and whitespace checks pass.
No live trading, deployment, production recovery, or real lock release was performed.

## Durable dispatch recovery (subsequent implementation)

ExecutionService.recover(token) now handles prepared-only attempts with lost
responses, accepted open/partial orders, and uncertain amendments through an
explicit DispatchEvidence provider contract. The earlier terminal-only method is
retained for legacy acknowledged receipts. No automatic resubmission is performed.

Every new attempt persists a dispatch ID (the unique admission token), account
coverage generation, complete approved order, operation and original amendment ID
before transport. Submission and amendment transports receive the dispatch ID.
Providers without a reconciliation implementation remain blocked on uncertain
outcomes; matching terms and empty histories are never treated as evidence.

All four paper order managers implement idempotent dispatch using the new
paper_dispatches table. The approved order, account generation and full result
commit in the same transaction as cash, positions, orders and daily-risk events.
An identical dispatch returns its stored result without filling again. Reusing an
ID with different terms fails. Dispatch records survive account resets; an old
generation cannot be dispatched or recovered against a new account generation.
Normal schema initialization creates the table; no real database was migrated.

Paper recovery takes the same transactional write lock as dispatch. If the record
is absent after obtaining that lock, recovery inserts a durable rejection marker.
This is evidence of non-acceptance because it also fences a delayed sender: the
same ID cannot subsequently fill. A transaction still in progress must complete
or roll back before recovery can establish the result. SQLite and PostgreSQL use
the same behavior.

Open/partial recovery validates the exact dispatch identity and approved terms,
then requires a fresh complete account snapshot with the same order, status and
filled quantity. The remaining open exposure is reserved before admission unlocks.
Normal risk checks combine already-filled positions with the order's remaining
quantity. Accepted amendments replace their prior reservation; definitively rejected
amendments preserve the original. Terminal outcomes require authoritative terminal
identity. Inconsistent, stale, missing or reset-generation evidence keeps admission
blocked. Provider acceptance evidence must be final even if the order remains open.

The Redis recovery script atomically compares the token, attempt bytes, journal
bytes and persisted halt, writes the reconciled journal and result, then releases
only that lock. Normal acknowledgement persistence and lock release now also check
ownership atomically. A late sender cannot overwrite recovered state or delete a
new owner's lock. A Redis error can leave admission blocked; scripts do not imply
rollback on every Redis error. Inspect state before another recovery attempt.

### Operator flow

1. Halt trading and quiesce execution workers. Do not clear Redis keys manually.
2. GET /risk/execution/recovery to inspect the lock, attempt and reservations.
3. POST /risk/execution/recovery with {"token":"<observed lock token>"}.
   Both endpoints require risk:halt and write:orders permissions. The POST is audited.
4. Inspect the result. A successful recovery leaves the halt enabled; resume is a
   separate existing control operation. A lost recovery response returns 503 with
   instructions to inspect status. status=recovered with no matching held lock
   establishes that recovery completed. It is never an instruction to resubmit.
5. If evidence is unavailable, leave admission blocked and investigate the provider.

These are router-relative paths; deployments may mount the router under their
normal API prefix. No endpoint was called against a running user application.

### Scope and remaining limits

Historical limitation, superseded by `2026-11-11-paper-resting-orders.md`: the
paper simulator at this checkpoint filled immediately or rejected; it did not
simulate resting or partial orders. Open/partial and amendment recovery were qualified with
an authoritative deterministic venue fixture, while the Redis script itself ran
on real Redis. Live adapters do not yet implement the evidence contract and remain
blocked by their missing complete account-risk contract. Legacy prepared attempts
without dispatch IDs and orphan locks without attempt records require manual
investigation. The current Redis attempt is replaced by subsequent execution;
retain incident receipts separately. Redis durability/eviction configuration and
venue-side fencing remain operational requirements. Cluster hash-slot compatibility
was not qualified; the existing standalone Redis key scheme is unchanged.

### Final verification for durable dispatch recovery

- Real Redis 7.4.8 with SQLite/PostgreSQL and deterministic venue fixtures: 42 recovery
  tests passed. These cover duplicate/late dispatch, lost responses, transactional
  rollback, generation reset, remaining exposure, amendment acceptance/rejection,
  malformed/stale/provider-missing evidence, competing recovery workers, all four
  compare-and-set inputs, Redis wrong-type failure, lost recovery replies, late
  original acknowledgements, and the legacy terminal-only script.
- Existing real PostgreSQL paper integration: 12 passed, for 54 combined integration
  passes. PostgreSQL schemas and Redis test keys were confirmed empty after cleanup.
- Broad unit regression: 3,011 passed, two unchanged baseline failures, two startup
  checks deselected for separate execution (58.22 seconds).
- Startup integration: two passed. Real SQLite paper arbitrage integration: two passed.
- Baseline failures remain the external-feed-dependent sentiment test blocked by the
  socket guard and the calibration fixture with March dates outside the 30-day window.
  The two native ML suites were excluded because their combined process previously
  crashed in XGBoost; they were not rerun for this recovery change.
- Undefined-name lint and git whitespace checks passed. Both disposable containers
  and their anonymous volumes were removed. No live trading, deployment, production
  migration, or user-application recovery was performed.

Source changes remain local and uncommitted. The test runner uses a copied source
tree and sanitized environment. The socket guard allows only the two exact local
ports assigned to these disposable services. Redis controls in the integration
qualification use actual Redis commands and Lua, not a mocked script interpreter.

Saved receipts: /Users/mspeicher/agent-memory-artifacts/recovery-20261111/.
