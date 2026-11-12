# Order outcome interpretation

Status: Q1–Q5 confirmed by the user; implemented and locally qualified.
See the [qualification](../audits/2026-11-12-order-outcome-interpretation.md).
Source snapshot: `b8d61c8bd103ec550e5ee1829ab860cb2d08081f`.
No production implementation, schema change, deployment, live trading or skill
publication is part of this document.

## Settled

1. First slice is behavior preserving: existing response shapes, exception
   types, statuses, messages and retry/recovery rules remain.
2. The Order outcome module owns execution facts only. Opportunity lifecycle
   policy and adapter formatting remain with their existing owners.
3. First migration covers the execution module, Opportunity router and paper fill
   reconciler. HTTP/WhatsApp gain contract tests; their production adapters and
   arbitrage policy remain unchanged.
4. Use separate validation, receipt inspection and failure inspection operations;
   do not add a second submission operation.

## Alternatives compared

### A. Two pure interpretation operations

Combine receipt validation and receipt facts; separately inspect failures.
Small interface, but forces callers to supply admitted quantity and use
execution validation even where their current read-only interpretation differs.
Locality improves, but leverage is limited for paper reconciliation.

### B. Separate validation and inspection — recommended

Three in-process operations, with names provisional until design agreement:

```python
validate_receipt(result, *, admitted_quantity)
receipt_facts(result)
failure_facts(error)
```

Validation reproduces the execution module's existing checks and error ordering.
Read-only receipt facts separately describe zero-fill rejection, open/terminal
state, measured values, and the router's exact complete-priced-fill predicate.
Failure facts preserve the distinction between definite rejection, unavailable
admission, and reported uncertainty without overriding separately observed
submission evidence.

Facts retain raw-value distinctions; validation must not normalize a receipt
in place or silently strengthen another caller's accepted inputs. No universal
success status, retry recommendation, configurable policy engine or new adapter
interface is introduced. Original receipts/exceptions remain available to the
existing caller policy and formatting code.

This provides depth at the seam without adding a second submission operation.
The implementation gives locality to factual interpretation; existing broker,
control-store and storage adapters keep their responsibilities.

### C. Caller-first outcome capsule

Add an opt-in submission operation returning receipt plus execution-owned
admitted quantity/facts, keeping the existing submission operation compatible.
High leverage for the router, but adds a submission interface and expands the
migration around transport ownership. Less appropriate for a first,
behavior-preserving slice.

## Final confirmation

Q1–Q4 are settled. The user confirmed shared understanding and authorized
implementation in Q5.

## Safety invariants

- This call being undispatched does not settle an earlier uncertain attempt.
  No outcome fact is permission to retry.
- Mark dispatch uncertainty before transport; clear only after existing receipt
  validation, reservation updates and atomic acknowledgement. Retain durable
  dispatch IDs, late-delivery fencing, admission locks and journals.
- Cancellation propagates with its existing lock/claim behavior.
- Preserve the zero-fill REJECTED early return, including empty order ID.
- Other receipts retain authoritative identity and finite/consistent quantity
  checks. FILLED quantity is compared to admitted quantity, not the initial
  Opportunity proposal.
- Execution validation does not currently require a positive finite fill price;
  the router's priced-fill test does. Preserve that separation and raw Decimal
  type checks.
- Terminal cancellation can retain fills. Preserve the different paper
  projection and legacy whole-position tracking decisions.
- A rejected amendment can leave the original order active.
- A lost acknowledgement can coexist with a durable fill. Recovery resolves the
  same dispatch; no resend is inferred.
- Filled reservations remain until an authoritative fresh snapshot observes
  them. Quantity sizing, risk checks and account generations are unchanged.

## Proposed implementation and verification sequence

1. Refresh the exact baseline and check concurrent work before implementation.
   PR #17 and Claude's separate PostgreSQL bootstrap work are not prerequisites
   or authorized merge targets for this design exploration.
2. Add characterization at existing caller interfaces for the supported outcome
   matrix, preserving current statuses, messages, responses and side effects.
3. Extract interpretation without changing dispatch sequencing. Preserve the
   existing exception import locations and class identity across all callers.
4. Replace factual predicates individually in the agreed first migration set.
   Do not route Opportunity transitions or adapter formatting into this module.
5. Exercise pre-dispatch refusal, retained earlier lock, timeout, cancellation,
   malformed receipt, risk resizing, accepted/partial/terminal partial fills,
   rejected amendments, bookkeeping failure and lost acknowledgement.
6. Keep existing caller regression tests, including their intentionally different
   lifecycle decisions. Test the new interface with real order models and
   exceptions; do not mirror private helpers.
7. Run the required full unit/storage checks and paper integration suites on
   SQLite and disposable PostgreSQL/real Redis. Independently review the pinned
   head before any proposed merge. No live provider/app startup is needed.

The initial source/design exploration ran no tests and changed no production
code. Implementation now has fresh local receipts in the linked qualification.
