# Opportunity offer capture

Status: Q1–Q4 confirmed; implemented and locally qualified.
See the [qualification](../audits/2026-11-12-opportunity-offer-capture.md).

Exploration snapshot: `b6d0b87d55945d6518b4930c938c9db47cacdbf3`.
Implementation base: `296ff7fec3671a58b03a61442396f32ad899faa4` (#22 landed
independently; the capture/approval modules were unchanged).

## Settled decisions

1. First slice concentrates capture and confirmation identity, preserving existing
   responses, expiry, quantity ceilings, durable revision checks, atomic claims,
   cancellation, and retry/recovery behavior. Approval/claim policy stays with
   its current owners.
2. Migrate both the approval module and WhatsApp prompting. HTTP approval remains
   ID-only/current-offer; WhatsApp confirmation remains bound to the offer shown.
3. Store-owned read-only capture is selected. Keep its existing ordered two-read
   sequence and return facts; caller-specific validation and claims stay put.

## Design alternatives

### A. Independent capture module

One module performs the ordered reads and supplies delayed, caller-specific
revision interpretations. It hides the shared sequence, but adds a module and
must expose two different revision interpretations to preserve existing behavior.

### B. Store-owned read-only capture — recommended

Add one capture operation to the existing Opportunity store, returning a captured
value with the loaded Opportunity, earlier offered revision/time, and access to
the loaded revision:

```python
capture = await store.capture_offer(opportunity_id)
opportunity = capture.opportunity
# Existing caller checks, messages and refusal precedence remain in place.
```

The operation preserves two separate sequential reads: offer identity first,
Opportunity second. It does not create an atomic snapshot, add a transaction,
renew an offer, claim, expire, approve, execute or retry anything. Database/read
exceptions propagate as before; missing or inconsistent facts remain available
for the caller's existing checks. It does not introduce a new refusal type.

Do not normalize legacy revision values or move validation ahead of existing
caller checks. Revision type checks, truthiness checks and equality differ
between the two callers and must remain observable in the same order. The
capture value is not execution authority or proof that the offer remains
current. Its enclosed Opportunity and Order remain mutable for existing sizing.

This adds modest depth at the existing storage seam: locality for persisted
revision knowledge and read choreography, with leverage across both callers.
SQLite and PostgreSQL already provide real adapters; no new adapter interface,
dependency, schema, stored JSON format or status is needed.

### C. Approver-owned capture

The approval module exposes read-only capture to both callers. This keeps offer
knowledge near confirmation, but WhatsApp preview currently works with no
approver instance; preserving that behavior requires a static capture operation
or another execution-independent entry point. It couples preview to the approval
module without improving storage ownership.

## Current behavior to preserve

- Capture reads `offer_identity(id)` before `load(id)`. Replacement between those
  reads must retain the same mismatch evidence. Combining reads into one SQL
  snapshot would change race-observable prompt behavior and is outside this slice.
- Durable save revisions distinguish replacements even when timestamps repeat.
  An Agent cannot supply reserved revision/order/offer metadata.
- Stored Order terms, not the legacy suggested-order summary, drive execution.
- Approval checks missing row, pending status, offer time, stored terms, loaded
  revision type/nonempty, revision equality, quantity, shown identity and expiry
  in that order, retaining current refusal reasons/details.
- WhatsApp prompt checks missing row, stored terms, offer time and revision
  truthiness/equality in that order. It does not start checking pending status,
  quantity validity or expiry before prompting in this slice.
- Preserve legacy malformed revision handling until the existing caller checks.
  Approval requires a nonempty string; WhatsApp preview currently checks truthy
  equality. Shared capture must not silently strengthen either caller.
- WhatsApp confirmation retains exactly the existing id/revision/offer-time
  payload and phone-scoped, consumed-on-confirm token behavior.
- Confirmation freshly captures again through the approver. The post-claim
  identity-only reread remains; a captured object is never executed directly.
- Positive quantity remains the sizing ceiling; zero delegates sizing. Preserve
  mutable Order adjustment, broker/account resolution and existing exit behavior.
- Preserve revision-bound pending-to-approved and pending-to-expired transitions,
  metadata/status CAS loops, cancellation shielding, claim release and unknown
  execution recovery. Router-recorded statuses survive conditional cleanup.
- Preview still works without an approver instance; confirmation still reports
  its existing unavailable message in that case.
- Preserve ADR-0012: inbound WhatsApp remains distinct from notification adapters.
  No live graduation, deployment or skill publication is in scope.

## Proposed verification

Before implementation, the current baseline passed 116 focused tests across
approval, WhatsApp, Opportunity storage and HTTP contracts. The current paper
integration allowlist passed all 420 tests using SQLite, disposable PostgreSQL
17 and real Redis 7.4.8. The intentional failure control exited 1, and all
disposable containers were removed. These are baseline receipts, not evidence
for an implementation that has not yet been written.

Once the design is confirmed:

1. Characterize combined invalid-state refusal precedence and prompt-only policy
   before extraction. Preserve exact external reasons/messages.
2. Test ordered capture through its interface with real SQLite/PostgreSQL stores,
   including replacement between reads, repeated timestamps, missing offers,
   legacy metadata and read failures. Keep durable revision/CAS tests intact.
3. Test WhatsApp prompt-to-replacement-to-confirmation through the real approver
   and paper execution path: stale confirmation must place no order; concurrent
   valid approval must dispatch at most once.
4. Retain expiry, shown identity, sizing ceiling, post-claim identity, claim and
   execution cancellation, halt, partial fills and lost-acknowledgement recovery
   scenarios. Update caller fakes only as needed for the new interface, without
   replacing real-flow tests with helper-call assertions.
5. Run the required full unit/storage checks and SQLite/PostgreSQL/real-Redis paper
   suites at the implementation head, followed by independent review and CI.

Baseline receipts are outside the checkout at
`/Users/mspeicher/agent-memory-artifacts/opportunity-offer-capture-20261112/`.

## Final confirmation

Q1–Q3 are settled. The user confirmed shared understanding and authorized
implementation and a PR for review in Q4.
