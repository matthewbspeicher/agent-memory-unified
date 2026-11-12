# Order outcome interpretation qualification

## Agreed scope

The user confirmed Q1–Q5 in the design exploration: preserve outward contracts
and all safety checks; separate execution facts from Opportunity lifecycle policy
and adapter formatting; migrate execution, the Opportunity router and paper fill
reconciliation first. No live trading, deployment, schema change or skill
publication is authorized. See the [plan](../plans/2026-11-12-order-outcome-interpretation.md).

## Implementation

`execution/outcome.py` provides separate receipt validation, read-only receipt
inspection and failure inspection. Existing exception classes and the numeric
validation implementation move with those rules; `execution/service.py` keeps
their existing import locations available as the identical class objects.

Validation retains the zero-fill rejection early return, authoritative identity,
recognized status, finite/consistent quantity checks, error ordering, messages
and chaining. It compares fills to the admitted quantity and returns the same
receipt without normalizing its fields. It adds no price requirement.

Receipt inspection supplies independent open/terminal, zero-fill refusal and
complete-priced-fill facts. The latter preserves the router's raw Decimal type,
positive quantity/price and finiteness checks. A terminal cancellation can still
retain fills. Paper reconciliation and legacy tracking retain their different
lifecycle decisions. Failure inspection checks unavailable exceptions before
their rejection parent, preserves the flag's existing truthiness, and does not
infer certainty from an ordinary exception or grant retry permission.

The execution module still owns admission, risk checks, lock acquisition and
release, durable dispatch identity, reservation updates and atomic
acknowledgement. Dispatch uncertainty still begins before transport and clears
only after acknowledgement. Cancellation handling, recovery fencing, account
generations and rejected-amendment handling are unchanged.

The first migration changes no production HTTP/WhatsApp adapter or arbitrage
policy. Their existing messages and response contracts are characterized,
including HTTP 503 for either kind of unavailable exception and WhatsApp's
existing failure wording. Improving that wording is a separate behavior change.

## Verification

Before extraction, 142 characterization/regression tests passed against the
original implementation. Added cases freeze raw receipt values and existing
price policy, invalid-receipt uncertainty after transport, blocked admission
with an earlier unresolved attempt, and HTTP/WhatsApp failure contracts.

After extraction, 252 focused tests passed across the new interface, admission,
real-admission caller tests, router, approvals and adapter contracts. The new
interface tests cover terminal partial fills, native Decimal distinctions,
unchanged validation errors/order, empty-ID rejection, unavailable-exception
precedence, unclassified errors and compatibility import identity.

No real application database, live broker, app lifespan or on-chain operation
is used. Local receipts are retained outside the checkout under
`/Users/mspeicher/agent-memory-artifacts/order-outcome-interpretation-20261112/`.

Final local checks passed: 3,377 unit/storage tests and 389 paper integration
tests using SQLite and disposable PostgreSQL 17/Redis 7.4.8. The collection
failure control exited 1 as intended, and all disposable containers were removed.
The final 252-case focused run also passed. Ruff passed for all changed
production modules and the new interface test file; diff whitespace was clean.

One facts-record precision refinement was made during verification: an uncertain
failure leaves current-call dispatch knowledge unspecified. It never asserts
that a dispatch occurred. Existing caller policy reads the same uncertainty flag
as before. Both complete local suites were rerun after that refinement.
