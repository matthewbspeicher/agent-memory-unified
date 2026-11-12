# Cumulative portfolio exposure

The shared risk boundary now measures cumulative gross dollar exposure for
MaxPortfolioExposure. Previously the rule measured only the proposed order's value.
For example, with $100,000 equity and a 1% cap, a $600 resting buy followed by a $500
buy is now rejected even though each order individually fits under $1,000.

## Calculation

The account snapshot provides actual holdings and complete open-order terms.
Redis reservations supplement orders not yet acknowledged by the provider; an order
already present in the snapshot is counted once. Each open order contributes only
its unfilled quantity. Terminal or old-generation reservations are pruned using the
existing authoritative evidence. An amendment excludes its old remainder and tests
the replacement remainder together with already-filled holdings.

For each full symbol identity, let H be signed held quantity, B all pending buy
quantities including the candidate buy, and S all pending sell quantities including
the candidate sell. Worst-case quantity is max(abs(H), abs(H+B), abs(H-S)). Sum its
conservatively priced dollar value over all symbols. Opposing orders cannot cancel
one another in the calculation. Pending exits cannot free existing exposure before
filling, but an exit that merely closes held quantity does not create another copy
of that position. Crossing through zero into a larger short/long is bounded too.

Every held/open symbol is freshly quoted through the existing price validator.
The bound includes current bid/ask/last, order limits and stop levels, applicable
trailing-buy distance and contract multiplier. The larger measured held unit value
is retained when it exceeds that quote bound. Options retain their existing default
100 multiplier. Futures require an explicit multiplier; zero/negative/nonfinite
multipliers are rejected instead of silently defaulted. Quote timestamps are checked
again after the awaited attempt write and inside the final dispatch guard.

Actual positions and dollar reservations are kept separate from the synthetic
quantity reservations used by other rules. Those existing rules retain their
behavior. Gross exposure is divided by positive measured account equity plus any
explicitly provided external balances. Supplied external positions add absolute
measured market values; missing/nonfinite valuations fail closed.

## Scope

The cap is account-scoped plus explicitly supplied external holdings/balances,
matching the existing authoritative risk-state contract. It does not discover or
aggregate other broker accounts or perform foreign-exchange conversion. Prices and
values must be in the account's dollar basis. A shared independent cap across all
broker accounts would require a complete consolidated snapshot contract.

Reservations are bounds at admission, not guarantees against subsequent gaps or
market movement. New admissions reprice existing exposure. An unbounded market/stop
order still uses the existing conservative current/trigger quote model. Halts,
daily limits and other rules continue to apply to exits; this adds no reduce-only
policy bypass. No automatic cash or margin buying-power system is introduced.

The existing paper ledger remains floating precision for monetary aggregates; this
change uses Decimal for risk calculations and detailed reservation terms.

## Validation

Final receipts below. No live trading, deployment, user-database migration, commit
or push was performed. Tests ran against copied source with sanitized environment
and outbound socket guards; real service tests allowed only two disposable local
ports.


- Real Redis 7.4.8, PostgreSQL 17 and SQLite: **174 passed**, including 18 new
  cumulative-exposure cases and all 156 prior recovery/reconciliation/handoff cases.
- Focused rule/boundary checks: **170 passed** (included in the unit total).
- Broad unit regression: **3,099 passed**, two unchanged baseline failures and
  two startup checks deselected for separate execution (75.23 seconds).
- Startup: **2 passed**. SQLite arbitrage: **2 passed**. Disjoint total:
  **3,277 passed**, two baseline failures.
- Coverage includes cumulative symbols, partial fills, partial cancellation,
  amendment replacement and price increases, lost acknowledgements/recovery,
  journal-only reservations, competing admissions, short/long and zero-crossing
  bounds, opposite pending orders, external gross values, malformed data,
  multiplier validation and exposure quote expiry during attempt journaling.
- Baseline failures remain the network-dependent Alpha Vantage sentiment test and
  the calibration fixture outside the current date window. The two native
  meta-learner suites retain their prior exclusion for a combined-process crash;
  they were not rerun for this change.
- Undefined-name lint and git whitespace checks passed. Disposable Redis keys and
  PostgreSQL schemas were empty after tests. Containers and volumes were removed.

Source remains local and uncommitted. Receipts:
`/Users/mspeicher/agent-memory-artifacts/portfolio-exposure-20261111/`.
