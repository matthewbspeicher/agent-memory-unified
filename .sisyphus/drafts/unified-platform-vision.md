# Unified Trading Platform - Bring Agents to Life

## User Vision
- **Arena**: Capital Tournament - Agents compete for capital allocation based on performance
- **Gym**: Full Training Loop - Agents train via parameter optimization, self-reflection, and stress testing
- **Priority**: Build all at once as independent modules

## Current State: What's Built

### Agent Framework (PRODUCTION READY)
| Component | Status | Files |
|-----------|--------|-------|
| Base classes | ✅ Done | agents/base.py |
| 30 Strategies | ✅ Done | strategies/*.py |
| 13 Active Agents | ✅ Configured | agents.yaml |
| SignalBus | ✅ Done | data/signal_bus.py |
| Consensus Router | ✅ Done | agents/consensus.py |
| MetaAgent | ✅ Done | agents/meta.py |

### Capital Allocation (PARTIAL)
| Component | Status | Files |
|-----------|--------|-------|
| Tournament Config | ✅ Exists | learning.yaml |
| Capital Governor | ✅ Exists | risk/engine.py |
| Kelly Sizing | ✅ Done | sizing/*.py |
| Performance Tracking | ✅ Done | agents/analytics.py |
| Health Engine | ✅ Done | risk/engine.py |

### Backtesting (BASIC)
| Component | Status | Files |
|-----------|--------|-------|
| BacktestEngine | ✅ Basic | data/backtest.py |
| Historical Replay | ✅ Basic | data/backtest.py |
| API Endpoints | ✅ Done | routes/backtest.py |
| Walk-Forward | ⚠️ Minimal | backtesting/walk_forward.py |

### Arbitrage (PARTIAL)
| Component | Status | Files |
|-----------|--------|-------|
| 5 Arb Strategies | ✅ Done | strategies/kalshi_*, polymarket_*, funding_rate |
| Cross-Platform | ✅ Done | strategies/cross_platform_arb |
| SpreadStore | ✅ Exists | storage/arbitrage.py |
| API Routes | ✅ Done | routes/arbitrage.py |

### Risk & Exits (PRODUCTION READY)
| Component | Status | Files |
|-----------|--------|-------|
| RiskEngine | ✅ Done | risk/engine.py |
| Kelly Sizing | ✅ Done | sizing/kelly.py |
| 8+ Exit Rules | ✅ Done | exits/rules.py |
| ExitManager | ✅ Done | exits/manager.py |

---

## Gaps: What's Missing

### Arena (Capital Tournament) - HIGH PRIORITY
| Gap | Priority | Description |
|-----|----------|-------------|
| Arena Class | 🔴 Critical | No dedicated Arena for competitive evaluation |
| Tournament Brackets | 🔴 Critical | No formal stage promotion/demotion system |
| ELO Rating | 🔴 High | Mentioned in consensus.py but not fully wired |
| Qualification Workflow | 🔴 High | No agent certification before live trading |
| Auto-Promotion | 🔴 High | learning.yaml config not connected to execution |
| Leaderboard | 🟡 Medium | RemembrArenaSync exists but sync-only |

### Gym (Training Loop) - HIGH PRIORITY
| Gap | Priority | Description |
|-----|----------|-------------|
| RL Environment | 🔴 Critical | No gym environment for agent training |
| Parameter Optimization | 🔴 Critical | AdaptiveTuner exists but basic (grid search only) |
| Self-Reflection Loop | 🔴 High | No automated learning from trades |
| Stress Test Scenarios | 🟡 Medium | No scenario injection (flash crash, gaps) |
| Monte Carlo Sim | 🟡 Medium | No confidence intervals for backtests |
| Cross-Validation | 🟡 Medium | No k-fold validation |

### Backtesting - MEDIUM PRIORITY
| Gap | Priority | Description |
|-----|----------|-------------|
| Multi-Agent Backtest | 🔴 High | Can't backtest consensus/ensemble |
| Parameter Sweep | 🔴 High | No automated parameter optimization |
| Walk-Forward Full | 🟡 Medium | walk_forward.py exists but minimal |
| Realistic Fills | 🟡 Medium | Basic slippage, no volume simulation |
| Regime Backtest | 🟡 Medium | Can't test regime-specific performance |

### Arbitrage - MEDIUM PRIORITY
| Gap | Priority | Description |
|-----|----------|-------------|
| Execution Wiring | 🔴 High | Dual-leg execution not fully connected |
| Real-time Dashboard | 🟡 Medium | No live spread monitoring UI |
| Unified DSL | 🟡 Medium | No abstract arbitrage framework |

---

## Key Configuration Files
- `trading/agents.yaml` - 13 active agents
- `trading/learning.yaml` - Tournament stages (Sharpe 1.5 → 1.8 → 2.0)
- `trading/risk.yaml` - Risk parameters
- `trading/trading_rules.yaml` - Session bias rules

---

## Research Findings

### From Explore Agents:
1. **30 strategy implementations** in trading/strategies/
2. **Agent framework complete** with SignalBus, consensus, routing
3. **Learning.yaml has tournament config** but not wired to execution
4. **AdaptiveTuner** exists for parameter adjustment but only evaluates pass-through rate
5. **BacktestEngine** is basic - single agent, simple simulation
6. **Capital Governor** exists in risk engine but not fully connected to tournament stages

### From Code Review:
1. Tournament stages defined in learning.yaml (Sharpe 1.5/1.8/2.0 thresholds)
2. No Arena class - just scattered components
3. No parameter optimization beyond basic grid search
4. No RL training loop
5. Execution pipeline exists but tournament promotion is manual

---

## Open Questions for User

### 1. Arena Specifics
- Should agents compete in real-time or on historical data?
- What's the promotion cadence? (daily, hourly, per-trade)
- Maximum stages? (currently 3 defined in learning.yaml)

### 2. Gym Specifics  
- What training paradigm? (RL, genetic algorithms, gradient-free optimization)
- Should agents learn from live trades or only backtests?
- Stress test scenarios to implement? (flash crash, volatility spike, gap open)

### 3. Backtesting Scope
- Need multi-agent backtest (consensus/ensemble)?
- Parameter optimization required?
- Walk-forward validation?

### 4. Arbitrage Priority
- Wire up dual-leg execution?
- Build real-time spread dashboard?
- Create unified arbitrage DSL?

---

## Test Infrastructure
- Test framework: pytest
- Unit tests: trading/tests/unit/
- Integration tests: trading/tests/integration/
- Test commands: `cd trading && pytest`

---

## Scope Boundaries (from discussion)
- INCLUDE: Arena (capital tournament), Gym (training loop), Backtesting, Arbitrage
- EXCLUDE: New broker integrations, UI components (unless needed for dashboard)
