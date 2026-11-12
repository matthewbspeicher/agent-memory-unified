# Opportunity revision and metadata integrity

## Request

Fix the stale metadata race identified in the final review of approvals PR #9.
Use durable revision checks and atomic updates, preserve existing behavior,
and test SQLite and PostgreSQL paper execution. No live trading, deployments,
or publication of the Agensi skill.

## Failure reproduced

At main `565a7d8800de6817d9877d9d2f012ef81cfa88ff`, two controlled SQLite
interleavings reproduced a row whose displayed `suggested_trade` quantity was
500 while `OpportunityStore.load()` returned executable quantity 5:

- A stale `mark_approvable` read/modify/write restored old reserved metadata.
  Its `updated_at` predicate could not distinguish same-second SQLite saves.
- `update_data` copied old reserved metadata into an unconditional full write,
  overwriting a replacement or erasing a newly published offer.

Neither reproduction submitted an order. They exercised the real store and SQL.

## Behavior after the change

Every successful save stores a fresh UUID revision in the existing `data` JSON.
The store generates the revision, strips any Agent-supplied one, and returns the
saved identity through the routed Opportunity's data. A replacement always gets
a new revision, even if its visible order terms are identical. Failed saves do
not grant a new identity. No database migration or new dependency is needed.

The router offers only the saved revision that passed its gates. An obsolete
router cannot offer a newer notify-only or gate-held replacement. Repeated offer
publication for the same revision does not refresh its age.

Offer publication and metadata patches use conditional SQL updates comparing
both the previously read status and the database's exact previous JSON text.
The comparison uses `CAST(data AS TEXT)` for both the read and the predicate,
including PostgreSQL JSONB's representation. It does not rely on timestamp
precision, JSON serialization ordering in Python, or a process-local lock.
On a metadata conflict the operation rereads current state. A bound operation
refuses a replacement revision; it never reapplies old reserved control fields.

`update_data` now merges a patch into current metadata instead of replacing all
ordinary metadata. Reserved execution keys always remain store-owned. Execution
callers name the revision they processed and pass only the fields they intend
to change. Concurrent disjoint patches therefore survive together.

Approval reads an offer's revision/time together, compares the loaded revision,
and binds its status claim, expiry, and claim release to that revision. WhatsApp
confirmation carries both the shown revision and time, so equal clock readings
cannot authorize a replacement. HTTP's existing approve-current-by-id contract
is preserved; this does not add a client-supplied revision to the HTTP API.

Older pending suggestions without a store revision remain stored and pending,
but must be freshly routed/offered before approval. Terminal opportunities,
paper balances, orders, fills, recovery IDs, tracking and exit rules are not
rewritten or migrated.

## Validation

- The pre-change reproduction is retained outside the checkout under
  `opportunity-revisions-20261112/reproduce_before.py` in the local artifact root.
- Unit/storage suite runs with all existing files included, without local
  exclusions for the previously problematic meta-learner or venv scanner tests.
- `tests/integration/test_opportunity_revisions.py` runs controlled interleavings
  on SQLite, PostgreSQL TEXT and PostgreSQL JSONB. SQLite writers use separate
  connections; PostgreSQL operations use a real pool with multiple sessions in
  a non-UTC time zone. Cases include replacements before/during offer reads,
  equal audit timestamps, metadata/offer conflicts, concurrent disjoint patches,
  revision-bound status transitions, restart persistence, and nullable legacy
  payloads.
- `tests/integration/test_paper_opportunity_approval.py` uses the real router,
  execution boundary, PaperBroker, durable paper store, fill reconciler and
  real Redis. It covers partial entry -> approved exit -> cancellation of the
  entry remainder; concurrent approvals; halt refusal; lost acknowledgement;
  a stale router attempting to offer a replacement; and a stale patch racing a
  replacement that subsequently fills with its own quantity and exit rules.
- Both integration files are in CI's explicit paper-only allowlist, alongside
  the existing storage, matching, commissions and recovery tests. Test services
  are disposable PostgreSQL 17 and Redis 7.4.8; quotes and notifications are
  local doubles. No live adapter, app deployment or actual message send is used.

Exact terminal test receipts and independent review results accompany the PR.
Current main includes Claude's PostgreSQL TIMESTAMP expiry PR #11 at
`95c333205de995c9cdc3f375f83cd47cc5693bab`. Its expiry binding and narrowly
gated retry are preserved; revision publication happens only after the
successful write and commit. Its PostgreSQL offer tests now supply the saved
revision. The combined CI allowlist includes those tests as well.

A separate pre-existing status-writing limitation remains: older router gate
decisions use unbound `update_status(id, REJECTED)` across router instances.
This patch binds approval status transitions but does not convert every legacy
status writer. That follow-up is distinct from the reproduced metadata races.
