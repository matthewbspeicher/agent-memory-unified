# Infinite City Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 

**Goal:** Implement the `infinite_city.py` environment combining a 2D resource grid with a text-based policy engine to test long-horizon planning.

**Architecture:** Environment inherits from `EscapeRoomEnvironment`. It manages an asynchronous `tick()` loop updating grid resources and processing policy decisions.

**Tech Stack:** Python 3.14, NumPy (for grid logic), asyncio.

---

### Task 1: 2D Infrastructure Grid & Resource Loop

**Files:**
- Create: `trading/competition/escape_rooms/infinite_city.py`
- Modify: `trading/competition/escape_rooms/factory.py`
- Test: `trading/shared/tests/test_infinite_city_engine.py`

- [ ] **Step 1: Write the failing test for grid initialization**

```python
from trading.competition.escape_rooms.infinite_city import InfiniteCityEnvironment

def test_city_init():
    env = InfiniteCityEnvironment(grid_size=10)
    assert env.grid_size == 10
    assert "Energy" in env.global_resources
    assert env.state == "ACTIVE"
```

- [ ] **Step 2: Implement the Base `InfiniteCityEnvironment`**

```python
from typing import Any, Dict, List
from .base import EscapeRoomEnvironment

class InfiniteCityEnvironment(EscapeRoomEnvironment):
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: config = {}
        self.grid_size = config.get("grid_size", 10)
        self.num_agents = config.get("num_agents", 1)
        self.state = "ACTIVE"
        self.winner = None
        self.cycle_count = 0
        
        # City State
        self.global_resources = {
            "Energy": 1000,
            "Water": 1000,
            "Public_Sentiment": 100,
            "Budget": 5000
        }
        self.active_policies = []
        self.match_log = []

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        agent_id = kwargs.get("agent_id", 0)
        
        if tool_name == "upgrade_infrastructure":
            resource = kwargs.get("resource_type")
            cost = kwargs.get("cost", 500)
            if self.global_resources["Budget"] >= cost:
                self.global_resources["Budget"] -= cost
                self.global_resources[resource] += 200
                self.match_log.append(f"Agent upgraded {resource} infrastructure.")
                return f"{resource} upgraded successfully."
            return "Error: Insufficient Budget."
            
        return f"Action not recognized: {tool_name}"

    def advance_cycle(self):
        """Simulates time passing."""
        self.cycle_count += 1
        self.global_resources["Energy"] -= 50
        self.global_resources["Water"] -= 50
        
        # Check collapse condition
        if self.global_resources["Energy"] <= 0 or self.global_resources["Water"] <= 0:
            self.state = "COLLAPSED"
            self.match_log.append(f"Systemic Collapse at Cycle {self.cycle_count}.")
            
    def get_state(self) -> str:
        return self.state
        
    def verify_flag(self, flag: str) -> bool:
        if self.winner is None: return False
        return flag == self.winner
```

- [ ] **Step 3: Register in Factory**
Register `infinite_city` in `_ROOM_TYPES` in `factory.py`.

- [ ] **Step 4: Run Tests and Commit**
Run `pytest trading/shared/tests/test_infinite_city_engine.py` and commit.

---

### Task 2: Governance Layer & Policies

**Files:**
- Modify: `trading/competition/escape_rooms/infinite_city.py`

- [ ] **Step 1: Implement `enact_policy` tool**

```python
# In execute_tool for InfiniteCityEnvironment
        if tool_name == "enact_policy":
            policy_text = kwargs.get("policy_text")
            target_metric = kwargs.get("target_metric") # e.g., 'Energy_Conservation'
            
            self.active_policies.append(policy_text)
            self.match_log.append(f"Policy Enacted: {policy_text}")
            
            # Simple policy effect parsing
            if target_metric == "Energy_Conservation":
                self.global_resources["Public_Sentiment"] -= 10
                return "Policy enacted. Sentiment decreased, but Energy drain reduced."
            
            return "Policy enacted."
```

- [ ] **Step 2: Update `advance_cycle` to respect policies**
Modify `advance_cycle` to check `self.active_policies`. If "Conservation" is active, reduce the Energy drain from 50 to 25.

- [ ] **Step 3: Add Governance Tests and Commit**
Add `test_governance_policy_effects` and commit.
