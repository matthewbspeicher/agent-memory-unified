# FinRL-X Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize the trading engine architecture to match FinRL-X capabilities by implementing Pydantic config validation, vectorbt-based backtesting, three-tier risk management, and multi-account broker interfaces.

**Architecture:** We will replace the current `dataclass`-based configuration with Pydantic for strict runtime validation. The backtesting engine will be extended to support `vectorbt` for vectorized performance. Risk management will be divided into `Order`, `Portfolio`, and `Strategy` tiers. Broker interfaces will support multi-account mapping.

**Tech Stack:** Python 3.12, Pytest, Pydantic, VectorBT, FastAPI.

---

### Task 1: Pydantic Configuration Refactor

**Files:**
- Modify: `trading/config.py`
- Test: `trading/tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_config.py
import pytest
from pydantic import ValidationError
from config import Config

def test_pydantic_validation():
    # Should raise ValidationError for invalid type
    with pytest.raises(ValidationError):
        Config(api_port="invalid_port")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_config.py::test_pydantic_validation -v`
Expected: FAIL with "Failed: DID NOT RAISE <class 'pydantic.ValidationError'>" or similar.

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/config.py
from pydantic import BaseModel, Field

class Config(BaseModel):
    api_port: int = 8080
    api_host: str = "127.0.0.1"
    # ... migrate other fields ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_config.py::test_pydantic_validation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/config.py trading/tests/unit/test_config.py
git commit -m "refactor: migrate configuration to Pydantic"
```

### Task 2: Three-Tier Risk Controls

**Files:**
- Create: `trading/tests/unit/test_risk/test_three_tier.py`
- Modify: `trading/risk/engine.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_risk/test_three_tier.py
import pytest
from unittest.mock import MagicMock
from risk.engine import RiskEngine

@pytest.mark.asyncio
async def test_three_tier_evaluation():
    engine = RiskEngine()
    trade_mock = MagicMock()
    portfolio_mock = MagicMock()
    
    # Check that evaluate handles order, portfolio, and strategy context
    result = await engine.evaluate_order(trade_mock, MagicMock(), MagicMock())
    assert result.passed
    
    port_result = await engine.evaluate_portfolio(portfolio_mock)
    assert port_result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_risk/test_three_tier.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/risk/engine.py
    async def evaluate_order(self, trade, quote, ctx):
        return await self.evaluate(trade, quote, ctx)
        
    async def evaluate_portfolio(self, portfolio_ctx):
        # Placeholder for portfolio-level risk (e.g. max exposure)
        return True
        
    async def evaluate_strategy(self, strategy_name, performance_metrics):
        # Placeholder for strategy-level risk (e.g. max drawdown limit)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_risk/test_three_tier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_risk/test_three_tier.py trading/risk/engine.py
git commit -m "feat(risk): implement three-tier risk evaluation structure"
```

### Task 3: VectorBT Integration for Backtesting

**Files:**
- Create: `trading/tests/unit/test_backtest/test_vectorbt.py`
- Create: `trading/backtesting/vectorbt_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_backtest/test_vectorbt.py
import pytest
import numpy as np
import pandas as pd
from backtesting.vectorbt_engine import run_vbt_backtest

def test_vectorbt_execution():
    prices = pd.Series(np.random.random(100) * 100)
    signals = pd.Series(np.random.choice([0, 1, -1], 100))
    result = run_vbt_backtest(prices, signals)
    assert 'total_return' in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_backtest/test_vectorbt.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/backtesting/vectorbt_engine.py
import vectorbt as vbt
import pandas as pd

def run_vbt_backtest(prices: pd.Series, signals: pd.Series) -> dict:
    entries = signals == 1
    exits = signals == -1
    
    pf = vbt.Portfolio.from_signals(prices, entries, exits)
    
    return {
        "total_return": float(pf.total_return()),
        "sharpe_ratio": float(pf.sharpe_ratio())
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_backtest/test_vectorbt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_backtest/test_vectorbt.py trading/backtesting/vectorbt_engine.py
git commit -m "feat(backtest): integrate vectorbt for vectorized performance"
```

### Task 4: Multi-Account Unified Broker Interface

**Files:**
- Create: `trading/tests/unit/test_broker/test_multi_account.py`
- Modify: `trading/broker/interfaces.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_broker/test_multi_account.py
import pytest
from unittest.mock import MagicMock
from broker.interfaces import MultiAccountBroker

def test_multi_account_routing():
    broker = MultiAccountBroker()
    mock_sub_broker = MagicMock()
    broker.register_account("ACC_1", mock_sub_broker)
    assert broker.get_broker("ACC_1") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_broker/test_multi_account.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/broker/interfaces.py
from typing import Any, Dict

class MultiAccountBroker:
    def __init__(self):
        self._accounts: Dict[str, Any] = {}
        
    def register_account(self, account_id: str, broker: Any):
        self._accounts[account_id] = broker
        
    def get_broker(self, account_id: str) -> Any | None:
        return self._accounts.get(account_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_broker/test_multi_account.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_broker/test_multi_account.py trading/broker/interfaces.py
git commit -m "feat(broker): support multi-account unified interface"
```
