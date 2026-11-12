# Exit handoff for partially filled paper entries

The paper exit monitor can now emit a triggered exit while its tracked entry still
has an unfilled remainder. It continues to suppress another outstanding exit.
The router prepares this handoff before previewing or submitting the close through
the existing shared risk boundary.

Preparation verifies the broker, account, symbol, opposite side, durable entry job,
order identity and account generation. Generation checks also run at exit
registration and paper dispatch, covering resets between those stages. Shadow
evaluation never enters the mutating handoff. It records the handoff and cancels the
entry under the paper ledger's owned transaction. Cancellation and matching share
that transaction boundary: a matching tick either commits first and is included,
or arrives after cancellation and cannot fill the remainder.

After terminal cancellation is confirmed, fill reconciliation projects the final
cumulative quantity and fees. Only then is the exit sized to the confirmed remaining
tracked position. Monitor exits retain full-position intent if the entry finishes
before preparation; explicitly smaller exits after a finished entry retain their
requested quantity. Cancellation, evidence or projection failures refuse the exit.
Retries tolerate already-cancelled entries and replayed fills. A restart can repeat
the same preparation without doubling fills or closing the old requested quantity.
An outstanding registered exit blocks another close.

The feature is enabled for the normal paper application with its fill reconciler.
Other monitor configurations retain their pending-order interlock. Live adapters
cannot participate in this handoff. Halts and ordinary risk limits still apply to
the closing submission. Preparation does not resume execution or clear uncertain
submission locks. A denied close leaves the entry cancelled and the filled position
tracked with its exit rules intact; later monitor scans can retry when allowed.

The handoff stores cancellation progress. It does not bypass the monitor's rule
reevaluation or cooldown after a restart, nor automatically resume a denied close.
The simulator still advances matching with explicit liquidity ticks.

The subsequent `2026-11-11-cumulative-portfolio-exposure.md` checkpoint addresses
R10 for the authoritative account and explicitly supplied external portfolio state.

The subsequent `2026-11-11-automatic-paper-matching.md` checkpoint adds the
managed paper matching/expiry driver and supersedes R1 below.

## Earlier Claude review

The report `/tmp/amu-claude-resting-review.md` describes the earlier resting-order
checkpoint. R2, R4 through R8, and the ordinary amendment refusal race in R3 were
fixed in that checkpoint or automatic fill reconciliation. This change also handles
PaperWriteNotStarted on the outer submit-dispatch transaction as a definite rejection.
R1 remains the documented explicit-tick simulator behavior; there is no background
market/liquidity driver. R9 per-fill fees, R10 cumulative dollar exposure and R11
unknown-cancel error mapping remain separate documented limitations, not resolved
by the entry/exit handoff. Live cancellation, WhatsApp and other unreviewed areas
are not claimed fixed.

## Validation

- Real Redis 7.4.8, PostgreSQL 17 and SQLite: **156 passed**. Includes 26 new
  handoff/dispatch cases plus the previous 130 matching/recovery/reconciliation cases.
- New cases cover long/short fractional closes, a fill racing cancellation,
  cancellation failure, restart retry, projection failure after cancellation,
  wrong-broker refusal, outstanding exits, actual monitor-to-router execution,
  definite dispatch non-writes, resets between preparation/registration/dispatch,
  shadow-mode nonmutation, explicit partial-close sizing and a completing entry.
- Broad unit regression: **3,078 passed**, two unchanged baseline failures,
  two startup tests deselected for separate execution (55.47 seconds).
- Final affected monitor/rules/router/boundary subset after the last sizing change:
  **108 passed**, included in the broad partition rather than added to the total.
- Startup: **2 passed**. SQLite arbitrage: **2 passed**. Disjoint total:
  **3,238 passed**, two baseline failures.
- Baseline failures remain network-blocked Alpha Vantage sentiment data and the
  date-sensitive calibration fixture. The two native meta-learner suites remain
  excluded because of the previously reproduced combined-process native crash.
- Undefined-name lint and git whitespace checks passed. Disposable Redis keys and
  PostgreSQL schemas were empty after tests; containers and volumes were removed.

All tests used copied source, sanitized environment and outbound socket guards;
only the exact two disposable local service ports were permitted for integration.
No live trading, deployment, user-database migration, commit or push was performed.
Changes remain local. Receipts:
`/Users/mspeicher/agent-memory-artifacts/partial-entry-exits-20261111/`.
