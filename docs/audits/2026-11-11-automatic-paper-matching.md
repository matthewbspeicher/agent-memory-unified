# Automatic paper matching and expiry

The normal agent-framework paper application now starts a managed matching driver.
Resting orders progress from fresh quote observations and their fills feed the
existing automatic trade/exit reconciliation. DAY orders expire from the UTC clock
without requiring a matching symbol, a quote, Redis availability or a manual tick.
An independent expiry loop continues while the matching loop awaits a slow feed.
Shutdown cancels and awaits both loops before closing providers and ledgers.

## Explicit simulation policy

Default paper settings (also available through the existing STA_ environment loader):

- paper_matching_enabled=true
- paper_matching_interval_seconds=1.0
- paper_matching_liquidity_per_quote=1.0
- paper_matching_allow_last_price=true

The driver supplies a finite simulated quantity per side, shared FIFO across orders
for that account and symbol. This is an explicit paper assumption, not measured
market depth. Quote.volume is never used as executable liquidity. Each provider
observation is consumed once, and only one automatic event per UTC wall-clock second
can consume liquidity for an account/symbol/generation. Polling faster or adding a
worker cannot repeatedly spend the same observation or the same time window.

For feeds with neither bid nor ask, an explicitly enabled last-price fallback uses
positive finite last as both simulated sides while preserving the provider's original
timestamp. Disabling paper_matching_allow_last_price requires positive valid bid/ask.
A one-sided, crossed, stale, future, mismatched or otherwise invalid quote is refused;
the driver does not invent a new observation time. The existing 30-second freshness
and five-second future-skew limits apply. Providers returning naive/missing times
remain unsupported until they supply valid evidence. A feed's retrieval timestamp
is not proof of exchange freshness; market calendars and actual depth are not modeled.

Disabling paper_matching_enabled retains manual matching and manual expiry APIs and
the existing fill reconciler. This opt-out disables both automatic driver loops.
No driver starts in live or worker mode, or when the agent framework is disabled.
Only PaperDispatchMixin managers owning this exact ledger participate; live managers
and foreign-ledger managers are excluded. Broker aliases are deduplicated.

## Atomicity, controls and recovery

Automatic event/sample identities are durable and scoped to the account, full symbol
and ledger generation. The window identity is selected under the owned ledger lock,
after bounded control reads. Sample/window receipts and all matching writes commit
or roll back together. A lost response or restart cannot consume that liquidity again.
New generations cannot receive fills from quotes fetched for old generations.
Old event receipts remain generation-bound rather than being reused on reset.

Fresh quotes are fetched outside the ledger transaction with bounded async timeouts.
Redis control reads are also bounded, including the final read under the ledger lock.
Only an explicit persisted false halt state permits automatic matching. Missing,
failed or halted controls block new matching but leave clock expiry available.
Expiry and matching failures are isolated by account/symbol and retried; cancelled
orders retain existing fills, fees and tracked positions. GTC orders do not expire.

The driver advances already-admitted paper orders. It never creates a new order,
resumes execution or clears an uncertain dispatch lock. Entry/exit submissions still
use the shared risk boundary. The existing finite-liquidity stop/limit matching,
cumulative commission and fill-reconciliation behavior is retained.

## Practical limits

All workers should use consistent paper settings. Polling cadence includes provider
latency; the independent expiry loop avoids quote-wait starvation but still shares
the bounded ledger transaction lock. Custom asynchronous providers must yield and
honor cancellation. Automatic ticks and receipts remain audit records; no retention
or compaction policy is introduced. Manual tick calls remain an independent explicit
liquidity source and should not be mixed into a running automatic simulation unless
additional test liquidity is intended.

No live trading, deployment, user-database migration, commit or push was performed.
Changes are local and uncommitted. Test services are disposable and isolated.

## Validation

- Real Redis 7.4.8, PostgreSQL 17 and SQLite: **232 passed**, including 42 new
  automatic matching/expiry cases plus all 190 prior cases (27.77 seconds).
- Broad unit suite: **3,115 passed**, two unchanged baseline failures and three
  startup tests deselected for separate execution (55.81 seconds).
- Startup: **3 passed**, including automatic-driver wiring and opt-out after the
  final lifecycle change. SQLite paper arbitrage: **2 passed**.
- Disjoint total: **3,352 passed**, two baseline failures.
- New cases cover all four paper adapters progressing without manual ticks,
  partial/full fills, reconciliation, same-quote replay and competing workers,
  stale/crossed/missing/mismatched/unavailable quotes, last-only policy,
  missing/halted controls, clock expiry, partial-expiry conservation and GTC,
  live-manager exclusion, control-read timeout, rollback/retry, reset during quote
  retrieval, broken-symbol isolation, independent expiry during hung quote lookup,
  managed task cancellation and invalid configuration.
- Baseline failures remain the socket-blocked external sentiment test and the
  date-sensitive calibration fixture. The two native meta-learner suites retain
  their prior combined-process-crash exclusion and were not rerun.
- Independent review identified control-read and window-selection gaps, both fixed
  before qualification. Undefined-name lint and git whitespace checks passed.
- Redis test keys and temporary PostgreSQL schemas were empty after tests.
  Disposable containers and volumes were removed.

Tests ran from copied source with sanitized environment and outbound socket guards.
Only the exact two local disposable service ports were permitted in integration.
No live quote feed was contacted during qualification.

Receipts: `/Users/mspeicher/agent-memory-artifacts/automatic-paper-matching-20261111/`.
