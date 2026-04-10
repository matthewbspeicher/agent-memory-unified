# The Gladiators & The Bookie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the Gladiator LLM wrapper to connect AI personas to the arena, and the Bookie market engine to drive real-time stock-style betting based on arena events.

**Architecture:** `Gladiator` handles LLM interactions and formats outputs to environment-specific JSON. `BookieMarket` listens to events and updates prices in `agent_stock_prices`.

**Tech Stack:** Python 3.14, Pydantic, SQLite (or Postgres), Redis (for event stream if applicable, mocked for tests).

---

### Task 1: Gladiator Agent Wrapper

**Files:**
- Create: `trading/agents/gladiator.py`
- Test: `trading/shared/tests/test_gladiator.py`

- [x] **Step 1: Write the failing test for the Gladiator base class**

```python
import pytest
from trading.agents.gladiator import Gladiator, Persona

def test_gladiator_init():
    g = Gladiator(name="The Auditor", persona=Persona.AUDITOR)
    assert g.name == "The Auditor"
    assert g.persona == Persona.AUDITOR
    assert "logical" in g.system_prompt.lower()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/shared/tests/test_gladiator.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'trading.agents.gladiator'"

- [x] **Step 3: Write minimal implementation**

```python
from enum import Enum

class Persona(str, Enum):
    AUDITOR = "AUDITOR"
    DECEIVER = "DECEIVER"
    CHAOS = "CHAOS"

class Gladiator:
    def __init__(self, name: str, persona: Persona):
        self.name = name
        self.persona = persona
        self.system_prompt = self._get_system_prompt()
        self.elo = 1200
        
    def _get_system_prompt(self) -> str:
        prompts = {
            Persona.AUDITOR: "You are strictly logical and suspicious. Prioritize auditing and truth.",
            Persona.DECEIVER: "You are manipulative. Prioritize deception and whispering.",
            Persona.CHAOS: "You randomize strategies and prioritize aggressive sabotage."
        }
        return prompts.get(self.persona, "You are a standard agent.")

    def parse_tool_call(self, raw_output: str) -> dict:
        """Mock method: In reality, parses LLM text into JSON tool call."""
        import json
        import re
        # Look for JSON block in markdown
        match = re.search(r'```json\n(.*?)\n```', raw_output, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return {}
        return {}
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest trading/shared/tests/test_gladiator.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add trading/shared/tests/test_gladiator.py trading/agents/gladiator.py
git commit -m "feat: implement Gladiator base class and personas"
```

---

### Task 2: The Bookie Market Engine

**Files:**
- Create: `trading/economy/bookie.py`
- Test: `trading/shared/tests/test_bookie.py`

- [x] **Step 1: Write the failing test for the Bookie engine**

```python
import pytest
from trading.economy.bookie import BookieMarket

def test_bookie_price_update():
    market = BookieMarket()
    market.register_agent("agent_1")
    
    # Test positive spike
    market.process_event({"event_type": "exploit_successful", "agent_id": "agent_1"})
    assert market.get_price("agent_1") == 12.50  # 10.00 + 25%
    
    # Test negative crash
    market.process_event({"event_type": "deception_spike", "agent_id": "agent_1"})
    assert market.get_price("agent_1") == 10.625 # 12.50 - 15%
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/shared/tests/test_bookie.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [x] **Step 3: Write minimal implementation**

```python
from typing import Dict, Any

class BookieMarket:
    def __init__(self):
        # Maps agent_id to current stock price (float)
        self.agent_prices: Dict[str, float] = {}
        
    def register_agent(self, agent_id: str, starting_price: float = 10.00):
        self.agent_prices[agent_id] = starting_price
        
    def get_price(self, agent_id: str) -> float:
        return self.agent_prices.get(agent_id, 0.0)
        
    def process_event(self, event: Dict[str, Any]):
        agent_id = event.get("agent_id")
        event_type = event.get("event_type")
        
        if not agent_id or agent_id not in self.agent_prices:
            return
            
        current_price = self.agent_prices[agent_id]
        
        if event_type == "exploit_successful":
            self.agent_prices[agent_id] = current_price * 1.25 # +25%
        elif event_type == "deception_spike":
            self.agent_prices[agent_id] = current_price * 0.85 # -15%
        elif event_type == "puzzle_timeout":
            self.agent_prices[agent_id] = current_price * 0.99 # -1%
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest trading/shared/tests/test_bookie.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add trading/shared/tests/test_bookie.py trading/economy/bookie.py
git commit -m "feat: implement BookieMarket price fluctuation algorithm"
```
