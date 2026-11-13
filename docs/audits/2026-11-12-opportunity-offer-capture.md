# Opportunity offer capture qualification

## Agreed scope

The user confirmed Q1–Q4 in the [design](../plans/2026-11-12-opportunity-offer-capture.md):
store-owned read-only capture, migrating approval and WhatsApp together while
preserving durable revisions, caller-specific checks/messages, claims, sizing,
cancellation and recovery. No live trading, deployment, schema change or skill
publication is authorized.

## Implementation

`OpportunityStore.capture_offer()` retains the existing two reads in their
existing order: offer identity first, loaded Opportunity second. It returns
their evidence in `CapturedOpportunityOffer`; mismatched, missing and malformed
revision facts are not normalized into a valid offer. No new SQL, transaction,
lock, retry or write is introduced.

The captured value has a frozen envelope, but its enclosed Opportunity and Order
remain mutable for existing sizing. Access to the loaded revision is deferred
until each caller's existing validation point, so capture does not preempt an
earlier refusal. Capture is neither a claim nor continued-currentness evidence.

The approver and WhatsApp caller no longer name the reserved revision metadata
key or implement the two-read choreography. They retain their distinct guards
and exact refusal order/messages. In particular, preview does not acquire the
approver's status/quantity/expiry checks or normalize legacy revision types.

The id/revision/offer-time confirmation payload is unchanged. Confirmation still
captures afresh through the approver; HTTP approval remains ID-only. Positive
quantity remains the sizing ceiling. Durable metadata/status CAS, claim
shielding/release, post-claim identity-only reread and execution/recovery paths
are unchanged. No captured Opportunity is reused to execute a later confirmation.

## Verification

Before extraction, 129 characterization/regression tests passed, including new
combined-invalid-state refusal precedence and limited-preview contracts. After
extraction, 133 focused tests passed across capture, approval, WhatsApp,
Opportunity storage and HTTP contracts. The capture tests exercise ordering,
original read failures without retry/write, missing/replacement evidence and
deferred revision access.

The paper integration suite passed 432 tests using SQLite, disposable PostgreSQL
17 and real Redis 7.4.8. New cases cover actual storage adapters with TEXT/JSONB
metadata, replacement between reads, unchanged offer freshness/status, legacy
revision values and mutable-but-unpersisted sizing changes. A real WhatsApp
prompt-to-confirmation flow rejects a replaced offer without placing an order;
fresh concurrent confirmations from two phones then place exactly one resting
paper order through the real approver, admission and ledger.

Existing partial fills, entry/exit handoff, commissions, exposure reservations,
claim cancellation, halt, lost acknowledgement, restart recovery and late-delivery
fencing tests remain. The collection failure control exited 1 as intended, and
all disposable service containers were removed.

Exploration baseline was `b6d0b87`; implementation incorporates independently
merged #22 at `296ff7f`. The early local runner retained the exploration SHA in
its static receipt field; qualification records the actual implementation base
and source hashes separately. Baseline receipts describe unchanged source and
do not substitute for implementation verification.

No real application database, app lifespan, external WhatsApp transport, live
broker or on-chain operation is used. Local receipts are retained outside the
checkout under
`/Users/mspeicher/agent-memory-artifacts/opportunity-offer-capture-20261112/`.

The required full unit/storage suite passed 3,428 tests (one existing skip, three
marker deselections). Ruff passed for changed production modules, the new capture
tests and both changed integration files; diff whitespace was clean.
