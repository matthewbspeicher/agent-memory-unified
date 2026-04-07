# Specification: Execution & Simulation (Paper Trading & Backtesting)

Implement risk-free validation and historical replay capabilities for the trading engine.

## Problem Statement
The signal pipeline is live, but there is no mechanism to execute trades without real risk or to verify strategy performance against historical data.

## Objectives
- **Paper Trading:** A risk-free simulation environment that tracks positions based on real-time signals and market prices.
- **Backtesting Engine:** A system to replay historical Taoshi positions against current strategies to calculate Sharpe ratio and Drawdown.

## Key Requirements

### 1. Paper Trading
- Implement `PaperBroker` class in `trading/broker/paper.py`.
- Simulate trade execution (fills) at current market prices.
- Track positions, balances, and PnL in the database.
- Controlled via `STA_PAPER_TRADING=true` environment variable.

### 2. Backtesting
- Build a replay engine to run closed Taoshi positions through active strategies.
- Verify performance metrics (Sharpe, Drawdown).

## Success Criteria
- [ ] `PaperBroker` can successfully "fill" trades and record them in the DB.
- [ ] Backtest engine can produce a performance report for a given time range.
- [ ] 100% test coverage for new execution logic.
