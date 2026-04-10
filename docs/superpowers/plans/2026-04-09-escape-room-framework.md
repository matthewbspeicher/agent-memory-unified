# Arena Gym - Escape Room Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational backend interfaces and execution loops for "Escape Room" logic puzzles, allowing AI agents to solve them via open-ended Tool Calling, and visualize the terminal output in the React frontend.

**Architecture:** A new `EscapeRoomEnvironment` Python interface governs the room state. The `ArenaMatch` engine routes agent tool calls to this environment and feeds the results back into the agent's context. The frontend `ArenaMatch.tsx` component is updated to render tool inputs/outputs as a terminal stream.

**Tech Stack:** Python (FastAPI), React 19 (TypeScript), Tailwind CSS

---

### Task 1: Database Model Updates

**Files:**
- Modify: `trading/competition/models.py`
- Modify: `trading/tests/unit/test_competition/test_escape_room_models.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_competition/test_escape_room_models.py
import pytest
from competition.models import ArenaChallenge, RoomType

def test_arena_challenge_escape_room_fields():
    challenge = ArenaChallenge(
        id="test-id",
        gym_id="gym-id",
        title="Escape Room 1",
        prompt="Solve the puzzle",
        difficulty_level="medium",
        xp_reward=500,
        max_turns=20,
        room_type=RoomType.DETERMINISTIC,
        config={"start_room": "kitchen"},
        flag_hash="098f6bcd4621d373cade4e832627b4f6" # "test"
    )
    assert challenge.room_type == RoomType.DETERMINISTIC
    assert challenge.config["start_room"] == "kitchen"
    assert challenge.flag_hash == "098f6bcd4621d373cade4e832627b4f6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && source .venv/bin/activate && pytest tests/unit/test_competition/test_escape_room_models.py -v`
Expected: FAIL (ImportError: cannot import name 'RoomType' from 'competition.models')

- [ ] **Step 3: Write minimal implementation**

Update `trading/competition/models.py`:
```python
from enum import Enum
from typing import Dict, Any, Optional

# Add near other Enums
class RoomType(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM_DRIVEN = "llm_driven"
    DOCKER = "docker"

# Modify ArenaChallenge to include the new fields
# Assuming ArenaChallenge is a Pydantic BaseModel or SQLModel
# Add these fields to the class:
    room_type: Optional[RoomType] = None
    config: Optional[Dict[str, Any]] = None
    flag_hash: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && source .venv/bin/activate && pytest tests/unit/test_competition/test_escape_room_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/models.py trading/tests/unit/test_competition/test_escape_room_models.py
git commit -m "feat(models): add escape room fields to ArenaChallenge"
```

---

### Task 2: Escape Room Base Interface & Deterministic Room

**Files:**
- Create: `trading/competition/escape_rooms/__init__.py`
- Create: `trading/competition/escape_rooms/base.py`
- Create: `trading/competition/escape_rooms/deterministic.py`
- Create: `trading/tests/unit/test_competition/test_deterministic_room.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_competition/test_deterministic_room.py
import pytest
from competition.escape_rooms.deterministic import DeterministicRoom

@pytest.mark.asyncio
async def test_deterministic_room_execution():
    config = {
        "nodes": {
            "start": {"description": "You are in a dark room. You see a door.", "tools": ["open_door"]},
            "outside": {"description": "You escaped!", "tools": ["submit_flag"]}
        },
        "flag": "victory123"
    }
    room = DeterministicRoom(config)
    
    # Check initial state
    assert room.get_state() == "You are in a dark room. You see a door."
    
    # Execute invalid tool
    res = await room.execute_tool("fly", {})
    assert "Unknown tool" in res
    
    # Execute valid tool to transition
    res = await room.execute_tool("open_door", {})
    assert "Transitioned" in res
    assert room.get_state() == "You escaped!"
    
    # Verify flag
    assert room.verify_flag("wrong") is False
    assert room.verify_flag("victory123") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && source .venv/bin/activate && pytest tests/unit/test_competition/test_deterministic_room.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# trading/competition/escape_rooms/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class EscapeRoomEnvironment(ABC):
    @abstractmethod
    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        pass
        
    @abstractmethod
    def get_state(self) -> str:
        pass
        
    @abstractmethod
    def verify_flag(self, flag: str) -> bool:
        pass

# trading/competition/escape_rooms/deterministic.py
from typing import Dict, Any
from .base import EscapeRoomEnvironment

class DeterministicRoom(EscapeRoomEnvironment):
    def __init__(self, config: Dict[str, Any]):
        self.nodes = config.get("nodes", {})
        self.current_node = config.get("start_node", "start")
        self.flag = config.get("flag", "")
        
    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        node = self.nodes.get(self.current_node, {})
        allowed_tools = node.get("tools", [])
        
        if tool_name not in allowed_tools:
            return f"Unknown tool or tool not allowed in this state: {tool_name}"
            
        if tool_name == "open_door":
            self.current_node = "outside"
            return "Transitioned to outside"
            
        return f"Executed {tool_name}"
        
    def get_state(self) -> str:
        return self.nodes.get(self.current_node, {}).get("description", "Unknown state")
        
    def verify_flag(self, flag: str) -> bool:
        return flag == self.flag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && source .venv/bin/activate && pytest tests/unit/test_competition/test_deterministic_room.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/competition/escape_rooms/ trading/tests/unit/test_competition/test_deterministic_room.py
git commit -m "feat(engine): implement base Escape Room interface and Deterministic Room"
```

---

### Task 3: Tool Execution Formatting in Frontend

**Files:**
- Modify: `frontend/src/pages/ArenaMatch.tsx`
- Create: `frontend/src/components/competition/TerminalOutput.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/competition/__tests__/TerminalOutput.test.tsx
import { render, screen } from '@testing-library/react';
import { TerminalOutput } from '../TerminalOutput';

test('renders tool call and result in terminal format', () => {
    render(<TerminalOutput toolName="run_sql_query" input='{"query": "SELECT * FROM users"}' output="3 rows returned" />);
    expect(screen.getByText('> run_sql_query')).toBeInTheDocument();
    expect(screen.getByText('3 rows returned')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test`
Expected: FAIL (File not found / test setup issues)

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/competition/TerminalOutput.tsx
import React from 'react';

interface TerminalOutputProps {
  toolName: string;
  input: string;
  output: string;
}

export function TerminalOutput({ toolName, input, output }: TerminalOutputProps) {
  return (
    <div className="bg-black border border-gray-800 rounded-lg p-4 font-mono text-[11px] overflow-x-auto shadow-inner mt-4 mb-4">
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-gray-800">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80"></div>
        </div>
        <span className="text-gray-500 font-bold ml-2">Terminal execution</span>
      </div>
      
      <div className="text-cyan-400 mb-1">
        <span className="text-emerald-500 mr-2">agent@sandbox:~$</span>
        <span className="font-bold">> {toolName}</span>
      </div>
      
      <div className="text-gray-400 mb-3 pl-4 border-l-2 border-gray-800">
        {input}
      </div>
      
      <div className="text-gray-300 whitespace-pre-wrap mt-2">
        {output}
      </div>
    </div>
  );
}
```

In `frontend/src/pages/ArenaMatch.tsx`, update the render loop to look for tool calls in the input/output string and optionally wrap them in the `TerminalOutput` component (or just use it for specific tool events if the backend sends structured JSON).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/competition/TerminalOutput.tsx frontend/src/pages/ArenaMatch.tsx
git commit -m "feat(ui): add TerminalOutput component for Escape Room tool visualization"
```
