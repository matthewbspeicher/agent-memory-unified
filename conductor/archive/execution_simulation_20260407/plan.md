# Implementation Plan: Execution & Simulation

## Phase 1: Paper Trading Architecture
- [x] Task: Create `PaperBroker` base class
    - [x] Define interface for buy/sell/close operations.
    - [x] Add unit tests in `trading/tests/unit/test_broker/test_paper.py`.
- [x] Task: Implement DB-backed position tracking
    - [x] Use `paper_positions` and `paper_orders` tables in `PaperStore`.
    - [x] Add `fill_price` and `exit_price` tracking (via `avg_fill_price` in orders).
- [x] Task: Integrate with `TradingEngine`
    - [x] Add `STA_PAPER_TRADING` toggle in `trading/config.py`.
    - [x] Switch `broker` instance based on toggle in `trading/api/startup/brokers.py`.
- [x] Task: Conductor - User Manual Verification 'Paper Trading' (Protocol in workflow.md)

## Phase 2: Backtesting Engine
- [x] Task: Build `ReplayEngine` (Taoshi Replay)
    - [x] Load historical signals/positions from `taoshi-vanta/validation/miners/`.
    - [x] Run them through strategy `scan()` logic via `TaoshiBacktestEngine`.
- [x] Task: Performance Reporting
    - [x] Calculate cumulative PnL, Sharpe, and Drawdown.
    - [x] Generate a JSON/Markdown summary (Saved to `backtest_results/`).
