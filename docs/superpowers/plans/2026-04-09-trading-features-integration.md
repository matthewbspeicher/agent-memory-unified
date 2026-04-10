# Snap-Back Trading Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Snap-Back scalping strategy, VWAP indicator, and bias-alignment filtering in the router.

**Architecture:**
- **Indicators:** Add VWAP calculation to `data/indicators.py`.
- **Strategy:** Create `strategies/snapback_scalper.py` using RSI(3), VWAP, and EMA(8).
- **Rules:** Update `rules/engine.py` with `volatility_above` (BB Width) and `DistanceToVWAPRule`.
- **Router:** Update `OpportunityRouter` to penalize/block signals contradicting the session bias.
- **Config:** Update `trading_rules.yaml` with the new strategy parameters.

**Tech Stack:** Python 3.14, FastAPI, Pandas/Numpy (for indicators), Pytest.

---

### Task 1: Implement VWAP Indicator

**Files:**
- Modify: `trading/data/indicators.py`
- Test: `trading/tests/test_indicators.py`

- [ ] **Step 1: Write the failing test for VWAP**

```python
def test_compute_vwap():
    from broker.models import Bar
    from decimal import Decimal
    bars = [
        Bar(timestamp=0, open=100, high=105, low=95, close=100, volume=10),
        Bar(timestamp=1, open=100, high=110, low=100, close=105, volume=20),
    ]
    # (100*10 + 105*20) / (10 + 20) = (1000 + 2100) / 30 = 3100 / 30 = 103.3333
    result = compute_vwap(bars)
    assert round(float(result), 4) == 103.3333
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest trading/tests/test_indicators.py::test_compute_vwap -v`
Expected: FAIL with `ImportError` or `NameError` for `compute_vwap`.

- [ ] **Step 3: Implement `compute_vwap` in `trading/data/indicators.py`**

```python
def compute_vwap(bars: list[Bar]) -> Decimal:
    if not bars:
        return Decimal("0")
    total_pv = sum(Decimal(str(b.close)) * Decimal(str(b.volume)) for b in bars)
    total_volume = sum(Decimal(str(b.volume)) for b in bars)
    if total_volume == 0:
        return Decimal("0")
    return total_pv / total_volume
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest trading/tests/test_indicators.py::test_compute_vwap -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/data/indicators.py trading/tests/test_indicators.py
git commit -m "feat: add vwap indicator calculation"
```

---

### Task 2: Add Volatility and Distance Rules to RulesEngine

**Files:**
- Modify: `trading/rules/engine.py`
- Test: `trading/tests/test_rules_engine.py`

- [ ] **Step 1: Write failing tests for new rules**

```python
def test_volatility_above_rule():
    engine = RulesEngine()
    rule = Rule(name="Vol High", condition="volatility_above", threshold=0.05)
    data = {"bb_width_pct": 0.06}
    result = engine.evaluate_rule(rule, data)
    assert result.passed is True

def test_distance_to_vwap_rule():
    engine = RulesEngine()
    rule = Rule(name="Near VWAP", condition="distance_to_vwap_below", threshold=1.5)
    data = {"price": 101, "vwap": 100} # 1% distance
    result = engine.evaluate_rule(rule, data)
    assert result.passed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest trading/tests/test_rules_engine.py -v`
Expected: FAIL with `KeyError` for unknown conditions.

- [ ] **Step 3: Implement rule evaluators in `trading/rules/engine.py`**

```python
# In RulesEngine.__init__ register:
# "volatility_above": self._eval_volatility_above,
# "distance_to_vwap_below": self._eval_distance_to_vwap_below,

def _eval_volatility_above(self, rule: Rule, data: dict) -> RuleResult:
    bb_width_pct = data.get("bb_width_pct", 0)
    passed = bb_width_pct >= rule.threshold
    return RuleResult(rule=rule, passed=passed, actual=f"{bb_width_pct}%", required=f">= {rule.threshold}%")

def _eval_distance_to_vwap_below(self, rule: Rule, data: dict) -> RuleResult:
    price = data.get("price", 0)
    vwap = data.get("vwap", 0)
    if not vwap: return RuleResult(rule=rule, passed=False, actual="N/A", required="vwap")
    dist = abs(price - vwap) / vwap * 100
    passed = dist <= rule.threshold
    return RuleResult(rule=rule, passed=passed, actual=f"{dist:.2f}%", required=f"<= {rule.threshold}%")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest trading/tests/test_rules_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/rules/engine.py trading/tests/test_rules_engine.py
git commit -m "feat: add volatility and distance-to-vwap rules"
```

---

### Task 3: Implement Snap-Back Scalper Strategy

**Files:**
- Create: `trading/strategies/snapback_scalper.py`
- Modify: `trading/trading_rules.yaml`
- Test: `trading/tests/test_snapback_strategy.py`

- [ ] **Step 1: Update `trading/trading_rules.yaml` with strategy config**

```yaml
scalping:
  snapback:
    rsi_period: 3
    rsi_oversold: 30
    rsi_overbought: 70
    ema_period: 8
    distance_threshold_pct: 1.5
    min_volatility_bb_width: 0.02
```

- [ ] **Step 2: Write the strategy logic in `trading/strategies/snapback_scalper.py`**

```python
from rules.models import RuleSet, Rule

def create_snapback_ruleset(config: dict) -> RuleSet:
    s = config["scalping"]["snapback"]
    return RuleSet(
        name="Snap-Back Scalper",
        entry_rules=[
            Rule(name="RSI(3) extreme", condition="rsi_below", threshold=s["rsi_oversold"]),
            Rule(name="Price near VWAP", condition="distance_to_vwap_below", threshold=s["distance_threshold_pct"]),
            Rule(name="Trend alignment (EMA8)", condition="ema_above", threshold=s["ema_period"]),
            Rule(name="Min Volatility", condition="volatility_above", threshold=s["min_volatility_bb_width"]),
        ]
    )
```

- [ ] **Step 3: Commit**

```bash
git add trading/strategies/snapback_scalper.py trading/trading_rules.yaml
git commit -m "feat: implement snapback scalper strategy and config"
```

---

### Task 4: Implement Bias-Alignment Filtering in Router

**Files:**
- Modify: `trading/agents/router.py`
- Test: `trading/tests/test_router_bias.py`

- [ ] **Step 1: Add bias alignment check to `OpportunityRouter`**

```python
# In OpportunityRouter.evaluate_opportunity:
def _apply_bias_alignment(self, opportunity: Opportunity, session_bias: str) -> float:
    # session_bias: "bullish", "bearish", "neutral", "mixed"
    if session_bias == "mixed" or not session_bias:
        return 1.0
    
    alignment = {
        ("LONG", "bullish"): 1.0,
        ("SHORT", "bearish"): 1.0,
        ("LONG", "bearish"): 0.8, # Penalty
        ("SHORT", "bullish"): 0.8, # Penalty
    }
    
    multiplier = alignment.get((opportunity.direction, session_bias), 1.0)
    
    if multiplier < 1.0 and self.config.get("risk_overlay", {}).get("require_bias_alignment"):
        return 0.0 # Block
        
    return multiplier
```

- [ ] **Step 2: Commit**

```bash
git add trading/agents/router.py
git commit -m "feat: implement bias-alignment filtering in router"
```
