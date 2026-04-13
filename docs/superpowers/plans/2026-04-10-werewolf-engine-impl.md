# AI Werewolf Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 

**Goal:** Implement the `werewolf.py` multi-agent engine, supporting 5-15 players with 4+ complex roles and a structured debate loop.

**Architecture:** A role-agnostic state machine inheriting from `EscapeRoomEnvironment`. Turn-based phases (Night, Dawn, Day, Vote, Post-match) with tool-routing to role-specific private contexts.

**Tech Stack:** Python 3.14, Pydantic, SQLite.

---

### Task 1: Environment & State Foundation [~]

**Files:**
- Create: `trading/competition/escape_rooms/werewolf.py`
- Modify: `trading/competition/escape_rooms/factory.py`
- Test: `trading/shared/tests/test_werewolf_engine.py`

- [x] **Step 1: Write the failing test for environment initialization**

```python
from trading.competition.escape_rooms.werewolf import WerewolfEnvironment

def test_werewolf_init():
    env = WerewolfEnvironment(num_agents=10)
    assert env.state == "PRE_GAME"
    assert len(env.roles) == 10
    assert "werewolf" in env.roles.values()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/shared/tests/test_werewolf_engine.py`

- [x] **Step 3: Implement the `WerewolfEnvironment` base and roles**

```python
from typing import Any, Dict
from enum import Enum
from .base import EscapeRoomEnvironment

class WerewolfState(str, Enum):
    PRE_GAME = "PRE_GAME"
    NIGHT = "NIGHT"
    DAWN = "DAWN"
    DAY = "DAY"
    VOTE = "VOTE"
    POST_GAME = "POST_GAME"

class WerewolfEnvironment(EscapeRoomEnvironment):
    def __init__(self, num_agents: int = 10):
        self.num_agents = num_agents
        self.state = WerewolfState.PRE_GAME
        self.roles = self._assign_roles(num_agents)
        self.alive_agents = list(range(num_agents))
        self.match_log = []

    def _assign_roles(self, n: int) -> Dict[int, str]:
        import math
        import random
        num_wolves = math.floor(n * 0.2)
        roles = ["werewolf"] * num_wolves
        if n >= 6: roles.append("seer")
        if n >= 8: roles.append("doctor")
        if n >= 10: roles.append("jester")
        roles.extend(["villager"] * (n - len(roles)))
        random.shuffle(roles)
        return {i: roles[i] for i in range(n)}
```

- [x] **Step 4: Register the environment in `factory.py`**

```python
# In trading/competition/escape_rooms/factory.py
from .werewolf import WerewolfEnvironment
_ROOM_TYPES["werewolf"] = WerewolfEnvironment
```

- [x] **Step 5: Run tests and commit**

Run: `pytest trading/shared/tests/test_werewolf_engine.py`
Commit: `feat: add WerewolfEnvironment and role assignment`

---

### Task 2: Night Phase & Private Tools

**Files:**
- Modify: `trading/competition/escape_rooms/werewolf.py`
- Test: `trading/shared/tests/test_werewolf_engine.py`

- [x] **Step 1: Implement the `kill`, `inspect`, and `protect` tool handlers**

```python
# In WerewolfEnvironment
async def execute_tool(self, agent_id: int, tool_name: str, params: Dict[str, Any]) -> str:
    role = self.roles.get(agent_id)
    if self.state == WerewolfState.NIGHT:
        if tool_name == "kill" and role == "werewolf":
            target = params.get("target_id")
            self.night_actions["kills"].append(target)
            return f"Agent {target} marked for kill."
        if tool_name == "inspect" and role == "seer":
            target = params.get("target_id")
            is_wolf = self.roles.get(target) == "werewolf"
            return "WEREWOLF" if is_wolf else "VILLAGER"
        if tool_name == "protect" and role == "doctor":
            target = params.get("target_id")
            self.night_actions["protected"] = target
            return f"Agent {target} is protected."
    return "Action not allowed in current state or for your role."
```

- [x] **Step 2: Write test for Seer inspection**

```python
async def test_seer_inspect():
    env = WerewolfEnvironment(num_agents=6)
    env.state = WerewolfState.NIGHT
    seer_id = [i for i, r in env.roles.items() if r == "seer"][0]
    wolf_id = [i for i, r in env.roles.items() if r == "werewolf"][0]
    res = await env.execute_tool(seer_id, "inspect", {"target_id": wolf_id})
    assert res == "WEREWOLF"
```

- [x] **Step 3: Run tests and commit**

Commit: `feat: implement night tools for werewolf, seer, and doctor`

---

### Task 3: Day Phase & Structured Debate Moderator

**Files:**
- Modify: `trading/competition/escape_rooms/werewolf.py`

- [x] **Step 1: Implement Phase Transitions and Moderator Prompts**

```python
# In WerewolfEnvironment
def next_phase(self):
    if self.state == WerewolfState.NIGHT:
        self.state = WerewolfState.DAWN
        self._process_night_results()
    elif self.state == WerewolfState.DAWN:
        self.state = WerewolfState.DAY
        self.debate_round = 0
    elif self.state == WerewolfState.DAY:
        if self.debate_round >= 2: # Max rounds
            self.state = WerewolfState.VOTE
        else:
            self.debate_round += 1

def get_moderator_prompt(self) -> str:
    if self.state == WerewolfState.DAY:
        # Structured Debate Logic
        import random
        target = random.choice(self.alive_agents)
        return f"Agent {target}, you have been accused of being a Werewolf. How do you respond?"
    return ""
```

- [x] **Step 2: Commit**

Commit: `feat: add phase transitions and debate moderator`

---

### Task 4: Vote & Win Conditions

**Files:**
- Modify: `trading/competition/escape_rooms/werewolf.py`

- [x] **Step 1: Implement the `vote` tool and victory check**

```python
# In WerewolfEnvironment
def execute_vote(self, votes: Dict[int, int]):
    from collections import Counter
    target, count = Counter(votes.values()).most_common(1)[0]
    self.alive_agents.remove(target)
    self.match_log.append(f"Agent {target} was voted out and was a {self.roles[target]}.")
    self._check_victory()

def _check_victory(self):
    wolves = [i for i in self.alive_agents if self.roles[i] == "werewolf"]
    town = [i for i in self.alive_agents if self.roles[i] != "werewolf"]
    if not wolves:
        self.state = WerewolfState.POST_GAME
        self.winner = "VILLAGERS"
    elif len(wolves) >= len(town):
        self.state = WerewolfState.POST_GAME
        self.winner = "WEREWOLVES"
```

- [x] **Step 2: Commit**

Commit: `feat: implement voting and victory conditions`
