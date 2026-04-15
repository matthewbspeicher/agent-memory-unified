# ADR-0010 — Strategy Graduation Gate (Paper → Live)

## Status

Accepted — 2026-04-14

## Context

Strategies in `trading/agents.paper.yaml` run with `action_level: auto_execute` against paper brokers. Strategies in `trading/agents.yaml` can run against live brokers (Kalshi, Polymarket, IBKR). There was no written criteria for promoting a strategy from paper to live.

Absent a gate, strategies graduate based on intuition. The 2026-04-14 prediction-market expansion review surfaced five proposed new strategies with claimed 2-15¢ edges and no backtest evidence — this ADR exists to make that kind of jump impossible going forward.

## Decision

Before a strategy may be added to `trading/agents.yaml` (or have its `action_level` raised to `auto_execute` there), it must satisfy **all** of:

1. **Backtest gate (offline evidence):**
   - ≥12 months of historical data
   - Sharpe ≥ 1.0 (per-trade, not annualised)
   - Hit rate ≥ 55%
   - Max drawdown ≤ 20% of deployed capital
   - Backtest notebook checked into `trading/backtest/notebooks/<strategy>.ipynb`

2. **Paper gate (live-market evidence):**
   - ≥30 calendar days in `agents.paper.yaml` with `action_level: auto_execute`
   - ≥50 filled paper trades
   - Paper Sharpe within 50% of backtest Sharpe (i.e. no severe live degradation)
   - Zero unexplained errors for the last 7 days

3. **Ops gate (risk plumbing):**
   - Strategy calls `KillSwitchRegistry.is_enabled` in `scan()` via the base guard (Task 6)
   - Position sizing honours `STA_PORTFOLIO_MAX_POSITION_USD` (Task 5)
   - Per-agent LLM cap set in `STA_LLM_AGENT_BUDGETS` if the strategy calls the LLM
   - Audit-log event fires on every emitted Opportunity

4. **Review gate:**
   - Written graduation request (ticket or PR description) lists backtest stats, paper stats, and ops-gate checkboxes
   - Reviewed by repo owner before merge

## Consequences

- Strategy proposals that can't pass the backtest gate never get built. This is intentional: the expansion review found multiple proposals (Congressional-trade alpha, Resolution Edge at 5-min polling, Market Making on thin PM books) whose claimed edges don't survive contact with historical data.
- The gate extends delivery time for new strategies by ~30 days (the paper-trading window). This is the point.
- Existing strategies on `agents.yaml` as of 2026-04-14 are grandfathered; the gate applies to new additions and to action-level promotions.

## Related

- `docs/plans/prediction-market-expansion-scope.md` — the proposal that motivated this ADR
- `docs/superpowers/plans/2026-04-14-prediction-market-phase-0-gates.md` — Phase 0 plan including this ADR
- `trading/backtest/prediction_market.py` — backtest harness (Task 2)
- `trading/risk/portfolio_cap.py` — portfolio cap (Task 5)
- `trading/strategies/base_guards.py` — kill-switch guard (Task 6)