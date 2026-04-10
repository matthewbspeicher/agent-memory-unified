# Go-Trader Incorporation - Feature Documentation

## Feature Name
Go-Trader Incorporation

## Status
Completed

## Owner
Sisyphus (AI Agent)

## Description
Incorporates key risk management, exit rules, and agent infrastructure from the go-trader project into the trading engine. Adds portfolio-level kill switch, consecutive loss circuit breaker, correlation enforcement, theta decay exits, agent concurrency limits, and strategy registry decorator.

## Implementation Summary

### 1. Portfolio-Level Kill Switch
**File:** `trading/risk/rules.py`, `trading/storage/portfolio_state.py`

Monitors portfolio drawdown from high-water mark (HWM). Blocks new trades when drawdown exceeds threshold.

**Configuration:**
```python
PortfolioDrawdownKillSwitch(
    max_drawdown_pct=25.0,  # Trigger at 25% drawdown
    cooldown_hours=24,       # 24-hour cooldown after trigger
    state_store=store,       # Optional: DB persistence
)
```

**Database:** `portfolio_state` table stores HWM and trigger state.

---

### 2. Consecutive Loss Circuit Breaker
**File:** `trading/learning/strategy_health.py`

Monitors consecutive losses per strategy. Throttles strategy when threshold exceeded.

**Configuration:**
```python
StrategyHealthConfig(
    enabled=True,
    max_consecutive_losses=5,
    consecutive_loss_cooldown_hours=48,
)
```

**Database:** `performance_snapshots` table tracks `consecutive_losses`, `max_consecutive_losses`, `consecutive_wins`, `max_consecutive_wins`.

---

### 3. Correlation Enforcement
**File:** `trading/risk/rules.py`, `trading/risk/correlation.py`

Blocks trades when portfolio correlation exceeds threshold. Uses Pearson correlation on price histories.

**Configuration:**
```python
MaxCorrelation(max_avg=0.7)  # Block if avg correlation > 70%
```

**Minimum tickers:** 2 (passes if fewer)

---

### 4. HTF Trend Filter
**File:** `trading/risk/rules.py`

Filters trades based on higher timeframe trend alignment. Supports SMA and EMA.

**Configuration:**
```python
HTFTrendFilter(
    htf_period=200,
    htf_sma=True,  # False for EMA
    direction="long",  # "long", "short", or "both"
)
```

---

### 5. Fee/Slippage Models
**File:** `trading/risk/rules.py`

Adjusts position sizing based on broker-specific fee and slippage estimates.

**Configuration:**
```python
FeeSlippageModel(
    fee_pct=0.001,      # 0.1% commission
    slippage_pct=0.0005, # 0.05% slippage
)
```

---

### 6. Theta Decay Exit Rules
**File:** `trading/exits/rules.py`, `trading/exits/manager.py`

Exit rule for prediction markets based on theta decay. Triggers on profit target, stop loss, or DTE threshold.

**Configuration:**
```python
ThetaDecayExit(
    entry_price=Decimal("0.50"),
    profit_target_pct=0.5,   # 50% profit target
    stop_loss_pct=2.0,       # 200% stop loss
    min_dte=2,               # Exit if DTE < 2
    expires_at=datetime,     # Contract expiry
    side="BUY",
)
```

**Default for prediction markets:** Added automatically via `ExitManager.compute_default_exits()`.

---

### 7. Agent Concurrency Limits
**File:** `trading/agents/runner.py`, `trading/agents/models.py`

Limits concurrent agent scans using semaphore. Configurable per-agent timeout.

**Configuration:**
```python
# AgentRunner
runner = AgentRunner(
    max_concurrent_scans=4,      # Semaphore limit
    default_scan_timeout=120.0,  # Default timeout (seconds)
)

# Per-agent timeout
AgentConfig(
    name="my_agent",
    scan_timeout=60.0,  # Agent-specific timeout
)
```

---

### 8. Strategy Registry Decorator
**File:** `trading/agents/decorators.py`

Decorator for registering strategy classes with metadata.

**Usage:**
```python
@strategy(
    name="momentum",
    description="Momentum-based trading strategy",
    timeout=300,
    default_params={"lookback": 20},
)
class MomentumStrategy:
    ...
```

---

## Database Migrations

### portfolio_state table
```sql
CREATE TABLE IF NOT EXISTS portfolio_state (
    key TEXT PRIMARY KEY,
    high_water_mark TEXT NOT NULL DEFAULT '0',
    triggered INTEGER NOT NULL DEFAULT 0,
    triggered_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### performance_snapshots columns
```sql
ALTER TABLE performance_snapshots ADD COLUMN consecutive_losses INTEGER DEFAULT 0;
ALTER TABLE performance_snapshots ADD COLUMN max_consecutive_losses INTEGER DEFAULT 0;
ALTER TABLE performance_snapshots ADD COLUMN consecutive_wins INTEGER DEFAULT 0;
ALTER TABLE performance_snapshots ADD COLUMN max_consecutive_wins INTEGER DEFAULT 0;
```

---

## Testing

### Unit Tests (44 new)
- `tests/unit/test_risk/test_portfolio_drawdown.py` (12 tests)
- `tests/unit/test_risk/test_correlation_gate.py` (9 tests)
- `tests/unit/test_learning/test_consecutive_losses.py` (4 tests)
- `tests/unit/test_exits/test_theta_decay.py` (10 tests)
- `tests/unit/test_agents/test_concurrency.py` (6 tests)

### Integration Tests (22 new)
- `tests/integration/test_portfolio_kill_switch_integration.py` (4 tests)
- `tests/integration/test_consecutive_loss_circuit_breaker.py` (4 tests)
- `tests/integration/test_correlation_enforcement.py` (4 tests)
- `tests/integration/test_theta_decay_exit_integration.py` (6 tests)
- `tests/integration/test_agent_concurrency_integration.py` (4 tests)

---

## Related
- Plan: `docs/plans/go-trader-incorporation-plan.md`
- Commit: 96a72e9 (test fixes)
