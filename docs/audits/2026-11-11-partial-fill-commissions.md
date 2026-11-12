# Commission accounting across partial fills

R9 is addressed for the existing paper fee models with per-order minimums.
IBKRFeeModel and FidelityFeeModel now calculate a cumulative fee target from executed
quantity and actual executed notional, then charge only the amount above commissions
already committed for that order. A first small IBKR stock fill charges the existing
$0.35 minimum; later small fragments charge zero until cumulative fees exceed it.
An amendment retains the order identity and its paid minimum. A new order has a new
minimum. Cancellation does not refund a minimum already charged on executed quantity.

## Model contract and durability

FeeModel.calculate remains unchanged for immediate full fills and existing callers.
The new calculate_incremental method defaults to the existing per-fill behavior.
IBKR and Fidelity explicitly opt into per-order aggregation. Custom FeeModel
subclasses, zero-fee and percentage-based models retain per-fill calculation and
rounding unless they explicitly opt into aggregation.

Matching reads cumulative quantity, exact price-times-quantity notional and paid fees
from detailed persisted fill events. It does not use the rounded order average or
process-local counters. Evidence must match the order's cumulative fill quantity.
The new fee delta is written with the fill, cash, position, risk event, cumulative
order result and tick receipt under the same owned transaction. Failed writes roll
back the charge. Identical tick replay returns the committed receipt without another
calculation; restart, amendment and uncertain-dispatch recovery retain the fee basis.

Existing reconciliation sums the incremental fees into cumulative order receipts,
entry fees, exit fees and realized PnL. It needs no separate fee projection or cache.
Zero commission on a later fragment is a valid fill, not a missing fee event.

## Scope

This preserves existing schedule constants and immediate-fill formulas; it does not
claim that those schedules match current live-broker tariffs. Per-order targets also
aggregate their existing rounding and regulatory caps. The percentage models retain
their existing per-fill rounding and do not acquire minimums.

No historical fee events are rewritten or refunded. Legacy partially filled orders
that already paid more than the cumulative target require investigation: a negative
increment is rejected rather than silently issuing a refund. Fee-model configuration
should remain consistent across a paper order's lifetime; this change does not add
a persisted fee-schedule version or migrate historic policies. Monetary aggregates
retain the paper ledger's prior floating-storage limitations; fill fee evidence is
decimal text.

No live trading, deployment, user-database migration, commit or push was performed.
Changes remain local and uncommitted.

## Validation

Final receipts below. Tests use copied source, sanitized environment and outbound
socket guards. Integration tests allow only the two disposable local service ports.


- Real Redis 7.4.8, PostgreSQL 17 and SQLite: **190 passed**, including 16 new
  commission cases and all 174 prior matching/exposure/recovery/handoff cases.
- Fee-model unit checks: **26 passed**, including 11 new cumulative-fee cases;
  these are included in the broad unit total.
- Broad units: **3,110 passed**, two unchanged baseline failures, two startup tests
  deselected for separate execution (58.75 seconds).
- Startup: **2 passed**. SQLite paper arbitrage: **2 passed**. Disjoint total:
  **3,304 passed**, two baseline failures.
- Tests cover minimum once, top-ups beyond minimum, mixed fill prices, option and
  sell regulatory formulas, per-fill custom/percentage compatibility, invalid fee
  evidence, replay/restart, amendment/cancellation/new orders, lost acknowledgements,
  recovery, write rollback and agreement between cash, daily PnL and tracked entry/
  exit fees through a closed position.
- Independent read-only review found no new accounting/recovery blocker.
- Baseline failures remain network-blocked Alpha Vantage sentiment data and the
  date-sensitive calibration fixture. The two native meta-learner suites retain
  their prior combined-process-crash exclusion and were not rerun.
- Undefined-name lint and git whitespace checks passed. Redis keys and temporary
  PostgreSQL schemas were empty after tests; disposable containers and volumes
  were removed.

Receipts: `/Users/mspeicher/agent-memory-artifacts/partial-fill-commissions-20261111/`.
