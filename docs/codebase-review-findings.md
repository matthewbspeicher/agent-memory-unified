# Codebase Review + Competitor Research Findings

**Date:** 2026-04-07
**Author:** Claude

---

## Part 1: Codebase Review Findings

### Critical Issues (Fix Immediately)

#### 1. Governor Async Path Never Called
**File:** `trading/risk/engine.py:79-82` + `trading/risk/governor.py:153-162`

The `CapitalGovernor.evaluate()` is synchronous and returns a stub. The actual logic is in `async_evaluate()` but it's **never called** by the risk engine. This means:
- Dynamic sizing based on Sharpe ratios NEVER runs
- Correlation guard is disabled
- Drawdown watchdog never triggers demotions

**Fix:** Either make `RiskEngine` support async rules, or implement a sync approximation of the governor logic.

#### 2. Bittensor Dual-Path Silent No-Op
**File:** `trading/integrations/bittensor/scheduler.py:310-316`

When `direct_query_enabled=False` AND `taoshi_validator_root` is not set, **all Bittensor data is silently skipped**. No warning is logged, no fallback activated.

**Fix:** Add explicit check that at least one path is active.

#### 3. Timing-Safe API Key Comparison Missing
**File:** `trading/api/auth.py:25`

```python
if api_key != settings.api_key:  # NOT timing-safe
```
Should use `hmac.compare_digest()` for timing-safe comparison.

---

### High Priority Issues

#### 4. Duplicate YAML Config Reads
**File:** `trading/api/app.py:1412-1414, 1696-1698`

`load_risk_config()` and `load_agents_config()` re-read YAML files even though already validated. Creates inconsistency windows.

#### 5. N+1 Query in Bittensor Evaluator
**File:** `trading/integrations/bittensor/evaluator.py:192-210`

```python
for hotkey, r in rollups.items():
    async with self.store._db.execute(
        "SELECT incentive_score FROM bittensor_raw_forecasts WHERE miner_hotkey = ?..."
    )  # N queries!
```
Should use `WHERE miner_hotkey IN (...)` with batch fetch.

#### 6. Sequential Health Recompute
**File:** `trading/learning/strategy_health.py:363-372`

```python
for name in agent_names:
    status = await self.evaluate(name)  # Sequential!
```
Should use `asyncio.gather()`.

---

### Medium Priority

#### 7. ExitManager Monitoring Loop Unverified
Cannot confirm `ExitManager` has an active monitoring task in production lifespan.

#### 8. Bittensor Reconnection Infinite Loop
**File:** `trading/integrations/bittensor/adapter.py:54-99`

No maximum total time limit on reconnection retries.

#### 9. Generic Exception Catches
**File:** `trading/agents/router.py:1346-1352`

Catches `Exception` including programming errors. Should distinguish retryable vs non-retryable.

---

### Low Priority / Technical Debt

- **Decimal inconsistency:** `router.py` uses both `_Decimal` and `_D` aliases
- **Duplicate import:** `app.py:1663` imports `timezone` twice
- **SignalBus prune O(n):** Could use heap for scalability
- **Sequential YAML reads:** Wasteful I/O

---

## Part 2: Competitor Research

### Key Competitors & What They Have

#### 1. FinRL / FinRL-X (14.7k stars)
**Strengths we should adopt:**
- **Modular architecture** - FinRL-X fully decoupled: data layer, algorithm layer, deployment layer
- **Professional backtesting** - Uses `bt` library (not custom)
- **Type-safe config** - Pydantic models with validation
- **Multi-account support** - Alpaca, Binance, etc.
- **Order/Portfolio/Strategy level risk controls** - Three-tier risk management

**Our gap:** We lack:
- Professional backtesting library integration (vectorbt, bt)
- Type-safe Pydantic config (we use dict-style config)
- Multi-account abstraction

#### 2. Vanta Network (Taoshi) - Our Subnet
**What they do:**
- Miner elimination on plagiarism + 10% max drawdown
- Debt-based scoring with weekly weight updates
- Carry fees + slippage simulation
- Probation period for low performers

**Our gap:** 
- We don't integrate with Vanta's elimination system
- No carry fee modeling
- No plagiarism detection

#### 3. Alpha Vantage
**What they offer:**
- 50+ technical indicators built-in
- Sentiment scores via AI/ML
- MCP server for AI agents
- Global market news API

**Our gap:**
- No built-in technical indicators library (we have some in agents)
- No sentiment score integration (our CryptoBERT is basic keyword-based)

---

## Part 3: Recommendations

### Immediate Actions (This Week)

1. **Fix Governor async path** - Critical for risk management working
2. **Add timing-safe API key comparison** - Security fix
3. **Add Bittensor path validation** - Prevent silent no-op
4. **Add async_gather to health recompute** - Performance fix

### Short-term (This Month)

5. **Integrate vectorbt/bt for backtesting** - Professional backtesting
6. **Add Pydantic config models** - Type safety
7. **Implement Vanta elimination integration** - Connect to real subnet behavior
8. **Add carry fee + slippage modeling** - Match Vanta's economics

### Medium-term (Next Quarter)

9. **Technical indicator library** - Add pandas_ta properly integrated
10. **Multi-account abstraction** - Unified broker interface
11. **Three-tier risk controls** - Order/Portfolio/Strategy level
12. **Plagiarism detection** - For miner signal uniqueness

---

## Summary Table

| Category | Our Status | Gap | Priority |
|----------|-----------|-----|---------|
| Risk Engine (Governor) | Broken async | Dynamic sizing disabled | CRITICAL |
| Bittensor Integration | Silent fail possible | No path validation | CRITICAL |
| API Security | Non-timing-safe | Security risk | CRITICAL |
| Backtesting | Custom walk_forward | Need professional lib | HIGH |
| Config | Dict-style | Need Pydantic | HIGH |
| Risk (3-tier) | Order-level only | Portfolio+Strategy | MEDIUM |
| Technical Indicators | Partial | 50+ AV missing | MEDIUM |
| Multi-account | Partial | Unified interface | MEDIUM |

---

## Files Referenced

| Issue | File | Line(s) |
|-------|------|---------|
| Governor async | `trading/risk/engine.py` | 79-82 |
| Governor sync stub | `trading/risk/governor.py` | 153-162 |
| Bittensor silent | `trading/integrations/bittensor/scheduler.py` | 310-316 |
| API timing | `trading/api/auth.py` | 25 |
| N+1 query | `trading/integrations/bittensor/evaluator.py` | 192-210 |
| Sequential health | `trading/learning/strategy_health.py` | 363-372 |
| YAML re-read | `trading/api/app.py` | 1412-1414 |
