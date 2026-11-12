# Paper resting orders and partial fills

Local implementation and isolated qualification only. No live trading, deployment,
user-database migration, commit or push was performed.

## Behavior

All four paper order managers share persisted matching behavior. Marketable orders
retain their existing immediate-fill path, slippage and fees. Unmarketable DAY/GTC
limits and untriggered stops now return SUBMITTED. Stop-limit triggers persist,
including when placement triggers the stop but the limit cannot fill. IOC orders
never rest; GTD is rejected because the order model has no expiry field.

`broker.orders.process_tick(quote, bid_size=..., ask_size=..., tick_id=...)` advances
resting orders explicitly. Liquidity is finite per side, shared FIFO across matching
orders, and never inferred from quote volume. Buy fills use ask; sells use bid.
Ticks require a fresh, timezone-aware, non-crossed positive quote and nonnegative
finite sizes. A tick predating acceptance cannot fill that order. DAY expiry uses
UTC calendar days and expires all account DAY orders when a new tick is processed.
There is no background tick driver or expiry scheduler. An idle simulator retains
orders until a tick or explicit cancellation. This is an end-to-end recovery test
facility, not a production exchange simulation.

Tick receipts are scoped to account and provider tick ID. Identical replays return
the original results without spending liquidity again, including after restart.
Changed payloads and old-generation replays are refused. Matching, trigger state,
fill evidence, cash, positions, cumulative order state and tick receipt commit or
roll back together under the existing SQLite/PostgreSQL transaction boundary.

Partial fills preserve cumulative quantity, weighted price and fees. Risk snapshots
cross-check full terms and linked fill evidence. Remaining exposure survives restart
and uncertain acknowledgements. An accepted order counts once per UTC day; a prior-day
order filling today also counts today. Cancellation preserves existing fills and
removes only remaining exposure. Amendments retain original acceptance time and
use the existing risk boundary, durable dispatch identity and recovery protocol.
A fill/cancel race that makes an amendment impossible returns a definite rejection.

PostgreSQL REAL columns are widened to DOUBLE PRECISION at paper-store initialization
to match SQLite's floating precision. This prevents float32 fractional quantities
from disagreeing with stored terms; it cannot recover historical rounding losses.
Only disposable test schemas were initialized here. Monetary aggregates still use
floating storage, not accounting-grade decimal columns. Detailed fill amounts and
order terms are stored as decimal text.

Automatic strategy fill reconciliation is implemented in the subsequent
`2026-11-11-automatic-fill-reconciliation.md` checkpoint. The limitations below
describe this earlier resting-order checkpoint.

## Review disposition and limitations

Claude's fresh read-only report is `/tmp/amu-claude-resting-review.md`; findings were
checked against the changing source rather than accepted as reproduced failures.
The implemented fixes cover account-scoped tick IDs, stop-limit trigger persistence,
clock-based cross-symbol DAY expiry, amendment races, PostgreSQL precision, pending
position-slot conservation, and the router's handling of non-final receipts.

The router records non-final execution receipts for reconciliation instead of
inventing a full entry, exit, or quality fill. Automatic propagation of later tick
fills into strategy trade tracking/exit rules is not implemented. Tick matching does
not call strategy callbacks. Marketable orders still fill immediately without a
liquidity budget. These limitations must be addressed before enabling unattended
paper strategy execution with resting orders.

Historical fee limitation, superseded for IBKR/Fidelity by
`2026-11-11-partial-fill-commissions.md`: fees retained the FeeModel interface's
per-fill calculation. Minimum fees may therefore
be charged for each partial fill; venue-specific per-order aggregation and maker
fees are not modeled. Legacy immediate order rows without fee detail still display
zero commission in reconstructed receipts; their daily risk events retain fees.
Existing portfolio-dollar-exposure rules are not cumulative buying-power controls.
Live-adapter cancellation, lifecycle routing and evidence contracts remain outside
this change; no live readiness claim is made.

## Validation

- Real Redis 7.4.8 plus temporary SQLite and PostgreSQL 17 schemas: **100 passed**.
  Of these, 46 cover actual resting/partial paper matching and recovery; 42 are
  existing dispatch recovery cases and 12 existing PostgreSQL execution cases.
- Broad unit regression: **3,045 passed**, two unchanged baseline failures and
  two startup tests deselected for separate execution (55.75 seconds).
- Startup integration: **2 passed**. SQLite paper arbitrage: **2 passed**.
- Total across disjoint partitions: **3,149 passed**, two baseline failures.
- Baseline failures: external Alpha Vantage sentiment data blocked by the network
  guard; calibration fixture dates outside the current 30-day window.
- The two native meta-learner suites remain excluded. An initial broad invocation
  excluded the wrong second file and reproduced the known native-process crash;
  the final invocation excludes both competition and learning meta-learner suites.
  No new passing claim is made for those suites.
- Undefined-name lint and git whitespace checks passed.
- Redis test keys and temporary PostgreSQL schemas were empty after tests. Both
  disposable containers and their volumes were removed.

Tests ran from a copied source tree with a sanitized environment. Only the exact
local disposable service ports were allowed for integration tests; unit tests
blocked outbound network access. Source changes remain local and uncommitted.
Receipts: `/Users/mspeicher/agent-memory-artifacts/resting-paper-20261111/`.
