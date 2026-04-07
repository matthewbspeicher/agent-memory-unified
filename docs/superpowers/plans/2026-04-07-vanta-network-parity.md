# Vanta Network Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align our paper trading simulation and miner evaluation engine with official Vanta Network economics (carry fees, realistic slippage) and miner lifecycle rules (elimination on drawdown, probation for underperformers).

**Architecture:** We will extend `PaperBroker` to deduct carry fees and simulate slippage using real order book depth. We will enhance `MinerEvaluator` to track miner peak-to-trough drawdowns and mark them for elimination or probation based on Vanta Subnet rules. 

**Tech Stack:** Python 3.12, Pytest, CCXT (for real slippage estimation), SQLite/PostgreSQL (for ranking state).

---

### Task 1: Vanta Economic Simulation (Carry Fees & Slippage)

**Files:**
- Create: `trading/tests/unit/test_broker/test_vanta_economics.py`
- Modify: `trading/broker/paper.py`
- Modify: `trading/broker/models.py`

- [ ] **Step 1: Write the failing tests**

```python
# trading/tests/unit/test_broker/test_vanta_economics.py
import pytest
from decimal import Decimal
from broker.models import Position, Symbol, AssetType
from broker.paper import PaperAccountProvider

@pytest.mark.asyncio
async def test_carry_fee_deduction(paper_store):
    # Setup mock account with $10k
    account = PaperAccountProvider(paper_store)
    # Mock position held overnight
    pos = Position(
        symbol=Symbol(ticker="BTCUSD", asset_type=AssetType.CRYPTO),
        quantity=Decimal("1.0"),
        avg_cost=Decimal("50000"),
        current_price=Decimal("50000")
    )
    # Trigger daily carry fee (e.g., 0.01% per day)
    fee_applied = await account.apply_carry_fees([pos])
    assert fee_applied == Decimal("5.0") # 50000 * 0.0001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_broker/test_vanta_economics.py -v`
Expected: FAIL with "AttributeError: 'PaperAccountProvider' object has no attribute 'apply_carry_fees'"

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/broker/paper.py (Add to PaperAccountProvider)
    async def apply_carry_fees(self, positions: list[Position], daily_rate: Decimal = Decimal("0.0001")) -> Decimal:
        """Deduct holding costs for open positions overnight."""
        total_fee = Decimal("0")
        for pos in positions:
            position_value = abs(pos.quantity) * pos.current_price
            fee = position_value * daily_rate
            total_fee += fee
            
        # Deduct from paper cash balance in DB
        db = await self._store._get_db()
        await db.execute(
            "UPDATE paper_accounts SET cash = cash - ? WHERE account_id = ?",
            (float(total_fee), "PAPER")
        )
        await db.commit()
        return total_fee
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_broker/test_vanta_economics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_broker/test_vanta_economics.py trading/broker/paper.py
git commit -m "feat(broker): implement vanta-style carry fee economics"
```

### Task 2: Miner Lifecycle (Elimination & Probation)

**Files:**
- Create: `trading/tests/unit/test_integrations/test_vanta_lifecycle.py`
- Modify: `trading/integrations/bittensor/evaluator.py`
- Modify: `trading/integrations/bittensor/models.py`

- [ ] **Step 1: Write the failing tests**

```python
# trading/tests/unit/test_integrations/test_vanta_lifecycle.py
import pytest
from integrations.bittensor.evaluator import MinerEvaluator
from integrations.bittensor.models import MinerRankingInput

def test_miner_elimination_drawdown():
    evaluator = MinerEvaluator(None, None)
    
    # 15% drawdown (Vanta threshold is typically 10%)
    input_data = MinerRankingInput(
        miner_hotkey="miner_1",
        windows_evaluated=10,
        direction_accuracy=0.4,
        mean_magnitude_error=0.1,
        mean_path_correlation=0.0,
        raw_incentive_score=0.5,
        max_drawdown=0.15 
    )
    
    status = evaluator._determine_lifecycle_status(input_data)
    assert status == "eliminated"
    
def test_miner_probation():
    evaluator = MinerEvaluator(None, None)
    
    # High error, but hasn't hit DD limit
    input_data = MinerRankingInput(
        miner_hotkey="miner_2",
        windows_evaluated=20,
        direction_accuracy=0.2,
        mean_magnitude_error=0.5,
        mean_path_correlation=-0.2,
        raw_incentive_score=0.1,
        max_drawdown=0.05 
    )
    
    status = evaluator._determine_lifecycle_status(input_data)
    assert status == "probation"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && pytest tests/unit/test_integrations/test_vanta_lifecycle.py -v`
Expected: FAIL with "TypeError: unexpected keyword argument 'max_drawdown'" or missing method.

- [ ] **Step 3: Write minimal implementation**

```python
# In trading/integrations/bittensor/models.py
# Update MinerRankingInput to include max_drawdown
@dataclass
class MinerRankingInput:
    miner_hotkey: str
    windows_evaluated: int
    direction_accuracy: float
    mean_magnitude_error: float
    mean_path_correlation: float | None
    raw_incentive_score: float
    max_drawdown: float = 0.0  # Added field

# In trading/integrations/bittensor/evaluator.py
# Add to MinerEvaluator class
    def _determine_lifecycle_status(self, miner_data: MinerRankingInput) -> str:
        """Apply Vanta network rules for elimination and probation."""
        # 10% maximum drawdown elimination rule
        if miner_data.max_drawdown >= 0.10:
            return "eliminated"
            
        # Probation for consistent underperformance (e.g., <30% accuracy after 20 windows)
        if miner_data.windows_evaluated >= 20 and miner_data.direction_accuracy < 0.30:
            return "probation"
            
        return "active"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && pytest tests/unit/test_integrations/test_vanta_lifecycle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/tests/unit/test_integrations/test_vanta_lifecycle.py trading/integrations/bittensor/evaluator.py trading/integrations/bittensor/models.py
git commit -m "feat(bittensor): enforce vanta elimination and probation rules"
```
