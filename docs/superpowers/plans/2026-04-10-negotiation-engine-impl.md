# High-Stakes Negotiation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 

**Goal:** Implement the `negotiation.py` environment to test multi-objective optimization and persuasion via a timed M&A simulation with hidden liabilities.

**Architecture:** Environment inherits from `EscapeRoomEnvironment`. It maintains a shared JSON "Drafting Table", a strict 10-minute timer, and asymmetric tool access for Buyer vs. Seller.

**Tech Stack:** Python 3.14, Pydantic, asyncio (timer).

---

### Task 1: Negotiation Environment & Drafting Table

**Files:**
- Create: `trading/competition/escape_rooms/negotiation.py`
- Modify: `trading/competition/escape_rooms/factory.py`
- Test: `trading/shared/tests/test_negotiation_engine.py`

- [ ] **Step 1: Write the failing test for the negotiation engine**

```python
from trading.competition.escape_rooms.negotiation import NegotiationEnvironment, NegotiationState

def test_negotiation_init():
    env = NegotiationEnvironment(num_agents=2)
    assert env.state == NegotiationState.PRE_NEGOTIATION
    assert "Price" in env.contract_draft
    assert env.buyer_id is not None
    assert env.seller_id is not None
```

- [ ] **Step 2: Implement the Base `NegotiationEnvironment`**

```python
from typing import Any, Dict, List, Optional
from enum import Enum
import random
import time
from .base import EscapeRoomEnvironment

class NegotiationState(str, Enum):
    PRE_NEGOTIATION = "PRE_NEGOTIATION"
    NEGOTIATION_LOOP = "NEGOTIATION_LOOP"
    CLOSING = "CLOSING"
    POST_MORTEM = "POST_MORTEM"

class NegotiationEnvironment(EscapeRoomEnvironment):
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: config = {}
        self.num_agents = 2
        self.state = NegotiationState.PRE_NEGOTIATION
        
        # 0 is Buyer, 1 is Seller
        self.buyer_id = 0
        self.seller_id = 1
        
        self.contract_draft = {
            "Price": None,
            "Board_Seats": None,
            "IP_Ownership": None,
            "Non_Compete": None,
            "Liability_Cap": None
        }
        
        self.proposing_agent: Optional[int] = None
        self.winner = None
        self.start_time = None
        self.match_log = []

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        agent_id = kwargs.get("agent_id", 0)
        return f"Action not recognized: {tool_name}"

    def next_phase(self):
        if self.state == NegotiationState.PRE_NEGOTIATION:
            self.state = NegotiationState.NEGOTIATION_LOOP
            self.start_time = time.time()
```

- [ ] **Step 3: Register in Factory**
Register `negotiation` in `_ROOM_TYPES` in `factory.py`.

- [ ] **Step 4: Run Tests and Commit**
Run `pytest trading/shared/tests/test_negotiation_engine.py` and commit.

---

### Task 2: Shared Drafting Tools & Timer

**Files:**
- Modify: `trading/competition/escape_rooms/negotiation.py`

- [ ] **Step 1: Implement `propose_clause`, `sign_contract`, and `countersign`**

```python
# In execute_tool for NegotiationEnvironment
if self.state == NegotiationState.NEGOTIATION_LOOP:
    # Check 10-minute timer (600 seconds)
    if time.time() - self.start_time > 600:
        self.state = NegotiationState.POST_MORTEM
        self.match_log.append("TIME UP. Deal collapsed.")
        return "Error: Time has expired. The deal collapsed."
        
    if tool_name == "propose_clause":
        cat = kwargs.get("category")
        val = kwargs.get("value")
        pitch = kwargs.get("pitch", "")
        if cat in self.contract_draft:
            self.contract_draft[cat] = val
            self.match_log.append(f"Agent {agent_id} proposed {cat}={val}. Pitch: {pitch}")
            return f"Proposed {cat} = {val}"
        return "Error: Invalid category."
        
    if tool_name == "sign_contract":
        # Check if all clauses are filled
        if any(v is None for v in self.contract_draft.values()):
            return "Error: Cannot sign. All 5 clauses must have a value."
        self.proposing_agent = agent_id
        self.state = NegotiationState.CLOSING
        return "Contract proposed for final signature."

if self.state == NegotiationState.CLOSING:
    if tool_name == "countersign":
        if agent_id != self.proposing_agent:
            self.state = NegotiationState.POST_MORTEM
            self.match_log.append("Contract successfully signed by both parties.")
            return "Deal closed successfully!"
        return "Error: Cannot countersign your own proposal."
    elif tool_name == "reject_and_exit":
        self.state = NegotiationState.POST_MORTEM
        self.match_log.append(f"Agent {agent_id} rejected the final contract.")
        return "Deal rejected."
```

- [ ] **Step 2: Add tests for drafting and signing**
Write `test_contract_drafting_and_signing` and commit.

---

### Task 3: Audit & Disclosure Toolset (Asymmetric Tools)

**Files:**
- Modify: `trading/competition/escape_rooms/negotiation.py`

- [ ] **Step 1: Setup hidden liabilities and dossier**
In `__init__`, initialize `self.toxic_asset_location = random.choice(list(self.contract_draft.keys()))`.
Initialize `self.buyer_audits_remaining = 3`.

- [ ] **Step 2: Implement Buyer Tools (`audit_dossier`, `request_disclosure`, `flag_liability`)**
In `execute_tool`:
```python
if agent_id == self.buyer_id:
    if tool_name == "audit_dossier":
        if self.buyer_audits_remaining <= 0: return "Error: No audits remaining."
        self.buyer_audits_remaining -= 1
        # Mock dossier read
        target_doc = kwargs.get("id", 1)
        if target_doc == 3: # Mock hit
            return f"Dossier {target_doc} indicates high risk in {self.toxic_asset_location}."
        return f"Dossier {target_doc} looks clean."
    if tool_name == "request_disclosure":
        cat = kwargs.get("category")
        return f"Formal request sent to Seller regarding {cat}."
    if tool_name == "flag_liability":
        cat = kwargs.get("category")
        self.match_log.append(f"Buyer flagged {cat} as toxic.")
        return "Liability flagged for post-mortem audit."
```

- [ ] **Step 3: Implement Seller Tools (`disclose`, `mask_liability`)**
In `execute_tool`:
```python
if agent_id == self.seller_id:
    if tool_name == "disclose":
        truth = kwargs.get("truth", "Full")
        self.match_log.append(f"Seller disclosed with truth level: {truth}")
        return "Disclosure sent."
```

- [ ] **Step 4: Add tests for asymmetric tools and commit**
Write `test_buyer_seller_asymmetric_tools` and commit.
