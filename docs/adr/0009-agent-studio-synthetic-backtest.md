# ADR-0009: Agent Studio Backtest and Deployment

## Status

Accepted (Updated 2026-04-13: follow-ups implemented)

## Context

The Agent Studio (Forge & Lab) feature requires a backtest capability to validate agent configurations before deployment. The original plan proposed wrapping the existing `BacktestEngine` from `scripts/backtest_system.py` in a synchronous API endpoint.

Three issues prevented direct integration:

1. **Import fragility**: `BacktestEngine` uses `sys.path.append` for imports, making it unreliable to import from API code.
2. **Blocking I/O**: The backtest engine runs synchronous calculations that would block the FastAPI event loop.
3. **CLI coupling**: `BacktestEngine` was designed for CLI use with argparse, not as an importable library.

## Decision

**Refactor the backtest logic into an importable library module (`trading/backtest/engine.py`) and run it via `run_in_executor` to avoid blocking the event loop.**

The backtest endpoint calls the real `run_backtest()` function in a thread pool executor. Results carry `status: "real"` to distinguish from the earlier scaffold implementation. The frontend deploy button is gated on real results (scaffold results cannot be deployed).

For deployment, the deploy endpoint writes the agent entry directly to `agents.yaml` with `trust_level: "monitored"` and `schedule: "on_demand"`. A trading engine restart is required to activate the new agent.

## Consequences

### Positive

- Real backtest metrics (Sharpe, win rate, drawdown, equity curve) from actual engine logic
- No blocking of the event loop — backtest runs in thread pool
- Clean importable library (`backtest.engine`) with no `sys.path` hacks
- Deploy writes directly to `agents.yaml` — agent appears in roster after restart
- Duplicate agent name detection prevents accidental overwrites

### Negative

- Backtest still uses simulated market data (same random walk as the CLI tool), not historical exchange data
- Agent framework reload requires trading engine restart (no hot-reload yet)

### Neutral

- The `run_backtest()` function can later be swapped with a version that pulls real historical data without changing the API contract
- `trust_level: "monitored"` ensures deployed agents start in safe mode

## File Map

| File | Action | Description |
|------|--------|-------------|
| `trading/backtest/__init__.py` | New | Package init |
| `trading/backtest/engine.py` | New | Importable `run_backtest()` function |
| `trading/api/routes/drafts.py` | Modified | Real backtest via executor, deploy to agents.yaml |
| `frontend/src/pages/Lab.tsx` | Modified | Scaffold vs real gating, updated button text |
| `frontend/src/pages/Forge.tsx` | Modified | Fixed API response handling |
| `trading/tests/unit/test_backtest_engine.py` | New | 10 tests for backtest engine |
| `trading/tests/unit/test_draft_routes.py` | Modified | Deploy and backtest integration tests |

## References

- Original plan: `docs/superpowers/plans/2026-04-13-agent-studio-implementation.md`
- BacktestEngine source: `scripts/backtest_system.py` (CLI version, preserved)
- Importable library: `trading/backtest/engine.py`
- Draft API routes: `trading/api/routes/drafts.py`
