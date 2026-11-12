# Revision-aware router gate status writes

## Request and baseline

Review and merge #13 if clean, then make legacy router gate rejections
revision-aware. Preserve paper execution behavior and test SQLite/PostgreSQL.
No live trading, deployments, or publication of the Agensi skill.

#13's reviewed head was `b4d1ed599d3b10f12edfe72b220add09e765f434`;
its CI run `43294699096` passed backend, paper integration and frontend jobs.
The intervening #12 changes were commentary only. Both independent review
refreshes found no new blocker. #13 merged at
`73c8e94caf72b6d5b75018be5256380a8765eb07`, this change's baseline.

## Reproduced failure

Regime and higher-timeframe checks, plus `_finalize_pre_order_decision`, wrote
`REJECTED` by id without checking which saved revision or status they evaluated.
A delayed gate could therefore reject a newer pending, approved, resting/partial,
or executed suggestion sharing the id, enabling later re-routing in some cases.

Before the fix, 36 controlled interleavings failed on the actual store: three
gates, four replacement states, and SQLite/PostgreSQL TEXT/PostgreSQL JSONB.
The repro did not submit orders or use external market data. Nine additional
regressions reproduced retargeting when the same Opportunity instance was reused
for a new save while a gate was awaiting other work.

## Change

The three pre-order rejection paths share `_reject_pre_order`. Their immutable
target (id, revision, expected status) is captured before gate awaits, so reusing
the same mutable Opportunity object cannot retarget an older decision. It uses the
existing store's atomic `transition` with the evaluated revision and expected
pre-order status, rather than an unconditional status write.

- Route-time regime and timeframe gates may change only `PENDING` to `REJECTED`.
- An execution-stage gate may reject its own `PENDING` automatic execution or
  `APPROVED` human claim; it cannot regress a receipt/reconciled terminal state.
- Missing revisions do not fall back to an unbound write.
- A stale conditional write is ignored, and the blocked caller still stops.
  Refusing to write must never be interpreted as permission to execute. A
  storage error is logged and also stops the blocked route, including inside
  health-gate error handling; task cancellation still propagates.
- Shadow decision recording retains its existing behavior.

Order submission, cancellation, amendment, ledger accounting, fills, dispatch
recovery, exit rules and post-submission outcome writers are unchanged. The fix
uses #13's durable revision protocol without a schema or dependency change.

## Test design

`test_router_gate_revisions.py` runs in CI's explicit paper-only allowlist.
It checks all three stale gates against newer pending, approved,
reconciliation-required and executed revisions. It also checks status ownership
within one revision: a delayed pending gate cannot reject an approval's claim;
a current approved execution gate can reject its own claim; and a completed
status is preserved. Legitimate current pending rejections and shadow recording
remain covered. Storage cases use separate SQLite connections or pooled
PostgreSQL TEXT/JSONB sessions.

The end-to-end cases pause each old gate, approve a replacement through the real
router and risk boundary, partially fill it in the durable paper ledger, then
release the old rejection. The replacement must remain under reconciliation,
keep its tracked fill and exit rules, refuse re-saving/second approval, and
finish filling exactly once. Both SQLite and PostgreSQL use real disposable
Redis admission controls. Quotes and notifications are local doubles.

Unit regressions verify that an unversioned or stale gate stops without an
unconditional status write, and that a failed health-gate status write cannot
resume execution. Two existing admission caller cases now carry a saved revision
and assert the conditional rejection while retaining their real risk-boundary
and no-transport assertions. Existing gate tests now assert the conditional
transition and saved revision, preserving their original rejection/shadow
assertions.

Terminal test counts, review receipts and exact final head accompany the PR.
