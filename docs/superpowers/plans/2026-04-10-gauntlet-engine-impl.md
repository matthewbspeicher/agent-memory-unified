# Escape Room Gauntlet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 

**Goal:** Implement the `gauntlet.py` environment with advanced SQL/Network/Bug-Fix puzzles and the Shared Sandbox Manager for adversarial sabotage.

**Architecture:** The environment handles multi-agent concurrent state using `SharedSandboxManager`. Three advanced room types inherit from a puzzle interface inside `gauntlet.py`.

**Tech Stack:** Python 3.14, Pydantic, SQLite3 (in-memory).

---

### Task 1: Gauntlet Environment & Shared Sandbox

**Files:**
- Create: `trading/competition/escape_rooms/gauntlet.py`
- Modify: `trading/competition/escape_rooms/factory.py`
- Test: `trading/shared/tests/test_gauntlet_engine.py`

-[x] **Step 1: Write the failing test for the sandbox manager**

```python
from trading.competition.escape_rooms.gauntlet import GauntletEnvironment, SharedSandboxManager

def test_gauntlet_sandbox_init():
    env = GauntletEnvironment(num_agents=4, puzzle_type="sql")
    assert isinstance(env.sandbox, SharedSandboxManager)
    assert len(env.sandbox.locked_resources) == 0
    assert env.state == "ACTIVE"
```

-[x] **Step 2: Implement the Base `GauntletEnvironment` and `SharedSandboxManager`**

```python
from typing import Any, Dict, List
from .base import EscapeRoomEnvironment

class SharedSandboxManager:
    def __init__(self):
        self.global_state: Dict[str, Any] = {}
        self.locked_resources: Dict[str, int] = {} # resource_id: rounds_remaining
        self.system_alerts: List[str] = []

    def lock(self, resource_id: str, duration: int):
        self.locked_resources[resource_id] = duration
        
    def tick_locks(self):
        expired = []
        for res in self.locked_resources:
            self.locked_resources[res] -= 1
            if self.locked_resources[res] <= 0:
                expired.append(res)
        for res in expired:
            del self.locked_resources[res]

class GauntletEnvironment(EscapeRoomEnvironment):
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: config = {}
        self.num_agents = config.get("num_agents", 1)
        self.puzzle_type = config.get("puzzle_type", "sql")
        self.state = "ACTIVE"
        self.sandbox = SharedSandboxManager()
        self.winner = None

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        agent_id = kwargs.get("agent_id", 0)
        # Check locks before proceeding
        
        if tool_name == "lock_resource":
            target = kwargs.get("resource_id")
            self.sandbox.lock(target, 2)
            self.sandbox.system_alerts.append(f"Resource {target} locked by unknown.")
            return f"Locked {target} for 2 rounds."
            
        return "Action not recognized."
```

-[x] **Step 3: Register in Factory**
Register `gauntlet` in `_ROOM_TYPES` in `factory.py`.

-[x] **Step 4: Run Tests and Commit**
Run `pytest trading/shared/tests/test_gauntlet_engine.py` and commit.

---

### Task 2: Advanced Puzzle - SQL Data Breaker

**Files:**
- Modify: `trading/competition/escape_rooms/gauntlet.py`

-[x] **Step 1: Implement `SQLPuzzle` logic**

```python
class SQLPuzzle:
    def __init__(self):
        import sqlite3
        self.conn = sqlite3.connect(':memory:')
        self._seed_data()
        
    def _seed_data(self):
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE _tmp_v42 (id INT, user_hash TEXT)")
        cur.execute("CREATE TABLE _sys_x99 (hash TEXT, auth_token TEXT)")
        cur.execute("INSERT INTO _tmp_v42 VALUES (1, '0xABC')")
        cur.execute("INSERT INTO _sys_x99 VALUES ('0xABC', 'FLAG{sql_master}')")
        self.conn.commit()

    def execute_query(self, query: str) -> str:
        try:
            cur = self.conn.cursor()
            cur.execute(query)
            return str(cur.fetchall())
        except Exception as e:
            return f"SQL Error: {str(e)}"
```

-[x] **Step 2: Wire `execute_sql` tool into GauntletEnvironment**
If `puzzle_type == "sql"`, route `execute_sql` tool to `self.puzzle.execute_query()`.

-[x] **Step 3: Write Test and Commit**
Write `test_sql_puzzle_execution` and commit.

---

### Task 3: Advanced Puzzle - Network Infiltrator

**Files:**
- Modify: `trading/competition/escape_rooms/gauntlet.py`

-[x] **Step 1: Implement `NetworkPuzzle` logic**

```python
class NetworkPuzzle:
    def __init__(self):
        self.servers = {
            "server_A": {"ticket": "Use port 8080 on server_B"},
            "server_B": {"8080": "auth_token_xyz"},
            "mainframe": {"token_xyz": "FLAG{network_ghost}"}
        }
    
    def query_server(self, server_id: str) -> str:
        return str(self.servers.get(server_id, "Host unreachable"))
```

-[x] **Step 2: Add `query_server` tool handling and Commit**
Add routing in `GauntletEnvironment` and write test.

---

### Task 4: Sabotage & Fog of War

**Files:**
- Modify: `trading/competition/escape_rooms/gauntlet.py`

-[x] **Step 1: Implement `corrupt_resource` and `spoof_event` tools**

```python
# In GauntletEnvironment.execute_tool
if tool_name == "corrupt_resource":
    res = kwargs.get("resource_id")
    # For SQL: DROP TABLE or alter data
    # For Network: change server dict
    return "Resource corrupted."
elif tool_name == "spoof_event":
    msg = kwargs.get("message")
    self.sandbox.system_alerts.append(f"[SPOOF] {msg}")
    return "Event spoofed."
```

-[x] **Step 2: Commit**
Add tests for sabotage tools and commit.
