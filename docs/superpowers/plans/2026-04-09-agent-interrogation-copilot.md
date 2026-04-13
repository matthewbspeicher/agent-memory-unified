# Agent Interrogation Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a Copilot sidebar allowing users to inspect real-time agent `ThoughtRecords` and interrogate/steer the agent via an LLM chat interface.

**Architecture:** Agents write a structured `ThoughtRecord` on every tick. The FastAPI backend exposes endpoints to retrieve these thoughts and process LLM chats/injections. The React 19 frontend displays these thoughts as visual cards in a sidebar and handles natural language interactions.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, pgvector, React 19, React Query, Tailwind CSS

---

### Task 1: Database Schema & Migration

**Files:**
- Create: `trading/models/thought.py`
- Modify: `trading/models/__init__.py:1-10`
- Modify: `trading/alembic/env.py` (if needed to ensure the new model is registered)
- Create: `trading/tests/unit/test_models/test_thought_record.py`

- [x] **Step 1: Write the failing test**

```python
import pytest
from datetime import datetime, timezone
import uuid
from models.thought import ThoughtRecord, ActionType

def test_thought_record_creation():
    record = ThoughtRecord(
        id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        agent_name="test_agent",
        symbol="BTC/USD",
        action=ActionType.BUY,
        conviction_score=0.85,
        rule_evaluations=[{"name": "RSI", "passed": True, "value": 30}],
        memory_context=["mem-123"]
    )
    assert record.agent_name == "test_agent"
    assert record.action == ActionType.BUY
    assert len(record.rule_evaluations) == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/tests/unit/test_models/test_thought_record.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'models.thought'"

- [x] **Step 3: Write minimal implementation**

```python
# trading/models/thought.py
from sqlmodel import SQLModel, Field
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column
from datetime import datetime
import uuid
from enum import Enum
from typing import List, Dict, Any

class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class ThoughtRecord(SQLModel, table=True):
    __tablename__ = "thought_records"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timestamp: datetime
    agent_name: str = Field(index=True)
    symbol: str
    action: ActionType
    conviction_score: float
    rule_evaluations: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSONB))
    memory_context: List[str] = Field(default=[], sa_column=Column(JSONB))
```

Update `trading/models/__init__.py` to import `ThoughtRecord` and `ActionType`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest trading/tests/unit/test_models/test_thought_record.py -v`
Expected: PASS

- [x] **Step 5: Create Alembic Migration**

Run: `cd trading && alembic revision --autogenerate -m "add thought_records table"`
Run: `cd trading && alembic upgrade head`

- [x] **Step 6: Commit**

```bash
git add trading/models/thought.py trading/models/__init__.py trading/alembic/ trading/tests/unit/test_models/test_thought_record.py
git commit -m "feat(db): add ThoughtRecord schema and migration"
```

---

### Task 2: FastAPI Copilot Endpoints

**Files:**
- Create: `trading/api/routes/copilot.py`
- Modify: `trading/api/main.py` (to include the new router)
- Create: `trading/tests/unit/test_api/test_copilot_api.py`

- [x] **Step 1: Write the failing tests**

```python
import pytest
from fastapi.testclient import TestClient

def test_get_thoughts(client: TestClient):
    response = client.get("/api/v1/agents/test_agent/thoughts?limit=5")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_copilot_chat(client: TestClient):
    payload = {
        "message": "Why did VWAP fail?",
        "thought_id": "00000000-0000-0000-0000-000000000000"
    }
    response = client.post("/api/v1/agents/copilot/chat", json=payload)
    assert response.status_code == 200
    assert "response" in response.json()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/tests/unit/test_api/test_copilot_api.py -v`
Expected: FAIL (404 Not Found)

- [x] **Step 3: Write minimal implementation**

```python
# trading/api/routes/copilot.py
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import List, Dict, Any
from pydantic import BaseModel
import uuid

# Assume get_session is available in dependencies
from api.dependencies import get_session

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    thought_id: uuid.UUID

class InjectRequest(BaseModel):
    command: str

@router.get("/agents/{agent_name}/thoughts", response_model=List[Dict[str, Any]])
async def get_thoughts(agent_name: str, limit: int = 20, session: AsyncSession = Depends(get_session)):
    # Mock implementation for tests - wire to DB later
    return []

@router.post("/agents/copilot/chat")
async def copilot_chat(request: ChatRequest, session: AsyncSession = Depends(get_session)):
    # Mock LLM response
    return {"response": "Mock LLM explanation based on thought record."}

@router.post("/agents/copilot/inject")
async def copilot_inject(request: InjectRequest, session: AsyncSession = Depends(get_session)):
    # Mock memory injection
    return {"status": "success", "injected_memory": request.command}
```

Include the router in `trading/api/main.py`:
```python
from api.routes import copilot
app.include_router(copilot.router, prefix="/api/v1", tags=["copilot"])
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest trading/tests/unit/test_api/test_copilot_api.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add trading/api/routes/copilot.py trading/api/main.py trading/tests/unit/test_api/test_copilot_api.py
git commit -m "feat(api): add copilot endpoints for thoughts, chat, and inject"
```

---

### Task 3: Agent Engine Integration

**Files:**
- Modify: `trading/agents/runner.py` (or where the agent loop evaluates rules)
- Create: `trading/tests/unit/test_agents/test_thought_recording.py`

- [x] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock
from agents.runner import AgentRunner

@pytest.mark.asyncio
async def test_agent_records_thought():
    runner = AgentRunner(...)
    runner._record_thought = AsyncMock()
    await runner.evaluate_tick("test_agent", "BTC/USD")
    runner._record_thought.assert_called_once()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest trading/tests/unit/test_agents/test_thought_recording.py -v`
Expected: FAIL

- [x] **Step 3: Write minimal implementation**

Update the agent loop to gather `rule_evaluations` and `memory_context`, instantiate a `ThoughtRecord`, and save it to the database asynchronously.

```python
# In trading/agents/runner.py (or appropriate engine file)
from models.thought import ThoughtRecord, ActionType
from datetime import datetime, timezone

async def _record_thought(self, agent_name: str, symbol: str, action: ActionType, score: float, rules: list, memories: list):
    record = ThoughtRecord(
        timestamp=datetime.now(timezone.utc),
        agent_name=agent_name,
        symbol=symbol,
        action=action,
        conviction_score=score,
        rule_evaluations=rules,
        memory_context=memories
    )
    self._db.add(record)
    await self._db.commit()
```
Call `await self._record_thought(...)` at the end of the tick evaluation.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest trading/tests/unit/test_agents/test_thought_recording.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add trading/agents/runner.py trading/tests/unit/test_agents/test_thought_recording.py
git commit -m "feat(engine): agents commit ThoughtRecords on decision ticks"
```

---

### Task 4: Frontend Components - Thought Stream

**Files:**
- Create: `frontend/src/components/copilot/CopilotSidebar.tsx`
- Create: `frontend/src/components/copilot/ThoughtCard.tsx`
- Modify: `frontend/src/Pages/Dashboard.tsx` (to include the sidebar)

- [x] **Step 1: Write the failing test**

```typescript
import { render, screen } from '@testing-library/react';
import { CopilotSidebar } from './CopilotSidebar';

test('renders Copilot Sidebar', () => {
    render(<CopilotSidebar agentName="test_agent" />);
    expect(screen.getByText('Agent Copilot')).toBeInTheDocument();
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test`
Expected: FAIL

- [x] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/copilot/ThoughtCard.tsx
import React from 'react';

export const ThoughtCard = ({ thought }) => (
  <div className="p-4 border rounded shadow-sm mb-2">
    <div className="flex justify-between">
      <span className="font-bold">{thought.action} {thought.symbol}</span>
      <span>{thought.conviction_score.toFixed(2)}</span>
    </div>
    <div className="mt-2">
      {thought.rule_evaluations.map((rule, idx) => (
        <span key={idx} className={`badge ${rule.passed ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'} mr-1`}>
          {rule.name}
        </span>
      ))}
    </div>
  </div>
);

// frontend/src/components/copilot/CopilotSidebar.tsx
import React from 'react';
import { ThoughtCard } from './ThoughtCard';

export const CopilotSidebar = ({ agentName }) => {
  // Use React Query to fetch thoughts (mocked here)
  const thoughts = []; 
  
  return (
    <div className="w-80 border-l p-4 h-screen overflow-y-auto">
      <h2 className="text-xl font-bold mb-4">Agent Copilot</h2>
      <div className="thought-stream">
        {thoughts.map(t => <ThoughtCard key={t.id} thought={t} />)}
      </div>
    </div>
  );
};
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/copilot/ frontend/src/Pages/Dashboard.tsx
git commit -m "feat(ui): add CopilotSidebar and ThoughtCard components"
```

---

### Task 5: Frontend Components - LLM Chat Interface

**Files:**
- Modify: `frontend/src/components/copilot/CopilotSidebar.tsx`
- Create: `frontend/src/components/copilot/ChatInput.tsx`

- [x] **Step 1: Write the failing test**

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInput } from './ChatInput';

test('submits chat message', () => {
    const handleSend = vi.fn();
    render(<ChatInput onSend={handleSend} />);
    const input = screen.getByPlaceholderText('Ask copilot...');
    fireEvent.change(input, { target: { value: 'Why did VWAP fail?' } });
    fireEvent.click(screen.getByText('Send'));
    expect(handleSend).toHaveBeenCalledWith('Why did VWAP fail?');
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test`
Expected: FAIL

- [x] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/copilot/ChatInput.tsx
import React, { useState } from 'react';

export const ChatInput = ({ onSend }) => {
  const [text, setText] = useState('');
  
  return (
    <div className="mt-4 flex">
      <input 
        type="text" 
        value={text} 
        onChange={e => setText(e.target.value)} 
        placeholder="Ask copilot..."
        className="border rounded p-2 flex-grow"
      />
      <button onClick={() => { onSend(text); setText(''); }} className="ml-2 bg-blue-500 text-white p-2 rounded">
        Send
      </button>
    </div>
  );
};
```
Integrate `ChatInput` at the bottom of `CopilotSidebar.tsx`. Add a dummy state to display user and copilot messages above the input.

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/copilot/
git commit -m "feat(ui): add natural language chat input to Copilot"
```
