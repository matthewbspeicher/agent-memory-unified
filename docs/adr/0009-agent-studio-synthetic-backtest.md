# ADR-0009: Agent Studio Synthetic Backtest Approach

## Status

Accepted

## Context

The Agent Studio (Forge & Lab) feature requires a backtest capability to validate agent configurations before deployment. The original plan proposed wrapping the existing `BacktestEngine` from `scripts/backtest_system.py` in a synchronous API endpoint.

Three issues prevented direct integration:

1. **Import fragility**: `BacktestEngine` uses `sys.path.append` for imports, making it unreliable to import from API code.
2. **Blocking I/O**: The backtest engine runs synchronous calculations that would block the FastAPI event loop.
3. **CLI coupling**: `BacktestEngine` was designed for CLI use with argparse, not as an importable library.

## Decision

**Use synthetic (randomized) metrics for v1, with a clear "scaffold" status indicator.**

The backtest endpoint returns realistic-looking metrics with `status: "scaffold"` to signal that results are not from real backtesting. The frontend displays a "SCAFFOLD" badge when this status is present.

This unblocks UI development and provides a working demo flow without pretending to have real backtesting capabilities.

## Consequences

### Positive

- Frontend can be developed and tested end-to-end
- API contract is established and can be iterated upon
- Clear communication to users that results are synthetic
- No blocking I/O or fragile imports

### Negative

- Users may deploy agents based on fake metrics if they ignore the "scaffold" indicator
- Does not validate actual agent performance

### Neutral

- The backtest endpoint contract (`POST /api/v1/drafts/{id}/backtest`) is real and will work when wired to actual backtesting
- The "scaffold" status can be removed when real backtesting is integrated

## Follow-up

Track these separately as future work:

1. **Real Backtest Integration** (Issue #TBD)
   - Refactor `BacktestEngine` into importable library
   - Run via background task (Celery/ARQ) or subprocess
   - Return actual metrics with `status: "real"`

2. **Agent Deployment** (Issue #TBD)
   - Write approved draft to `agents.yaml`
   - Trigger agent framework reload
   - Return deployment confirmation with agent name

## References

- Original plan: `docs/superpowers/plans/2026-04-13-agent-studio-implementation.md`
- BacktestEngine location: `scripts/backtest_system.py`
- Draft API routes: `trading/api/routes/drafts.py`
