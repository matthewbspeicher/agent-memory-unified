# Agent Interrogation Copilot Design

**Date:** 2026-04-09
**Status:** Approved for Planning

## 1. Overview
The Agent Interrogation Copilot is a widget-rich chat interface integrated into the unified React dashboard. It allows users to monitor, interrogate, and steer autonomous trading agents in real-time. Instead of relying on LLMs to hallucinate reasons for a trade, the system surfaces the objective, pre-computed `ThoughtRecord` of each tick (rules evaluated, memories recalled, scores) as visual widgets. LLMs are strictly used for natural language interrogation of these records and for parsing user commands to inject new memories or constraints.

## 2. Backend Data Model (FastAPI)

### 2.1 ThoughtRecord Schema
Agents will now commit a `ThoughtRecord` to PostgreSQL for every decision tick (buy, sell, hold). This provides a permanent, objective audit trail of the agent's "mind".

**Fields:**
- `id` (UUID)
- `timestamp` (DateTime)
- `agent_name` (String, foreign key to Agent)
- `symbol` (String)
- `action` (Enum: BUY, SELL, HOLD)
- `conviction_score` (Float 0.0-1.0)
- `rule_evaluations` (JSONB): Array detailing which rules passed/failed (e.g., `[{"name": "RSI(3) extreme", "passed": true, "value": 28}]`).
- `memory_context` (JSONB): Array of PGVector memory IDs and summaries retrieved during the tick.

### 2.2 Endpoints
- `GET /api/v1/agents/{agent_name}/thoughts?limit=20`: Fetches recent thought records.
- `POST /api/v1/agents/copilot/chat`: Accepts a user message and a `ThoughtRecord` ID. Uses an LLM to generate an explanation or response grounded strictly in the provided thought record.
- `POST /api/v1/agents/copilot/inject`: Parses user intent to add a new memory/rule to the agent's PGVector store.

## 3. Frontend Interface (React 19)

### 3.1 Copilot Sidebar
A sticky chat panel on the right side of the Agent detail view or the main Dashboard.

### 3.2 Widget Rendering (The "Stream")
The UI constantly polls or receives WebSocket events for new `ThoughtRecord` entries. These are rendered as visually distinct "Thought Cards" in the chat stream:
- **Header:** Timestamp, Action (BUY/SELL/HOLD), Symbol, Conviction Score.
- **Rule Badges:** Visual tags showing passed (green) and failed (red) rules.
- **Memory Links:** Clickable chips showing the context memories retrieved from the Knowledge Graph.

### 3.3 Natural Chat & Interrogation
At the bottom of the sidebar, users can type natural language queries:
- **Query:** "Why did the VWAP rule fail?"
  - *Flow:* The frontend calls `/chat` with the latest `ThoughtRecord`. The LLM reads the `rule_evaluations` JSON and explains that the distance was 1.8%, which exceeded the 1.5% threshold.
- **Steer/Inject:** "Avoid trading SPY around FOMC minutes."
  - *Flow:* The frontend calls `/inject`. The LLM parses the command into a new memory entry for SPY, which is immediately embedded via `pgvector` and affects the next tick.

## 4. Dependencies & Testing
- **Database:** Requires a new SQLAlchemy/SQLModel table and Alembic migration for `thought_records`.
- **LLM Context:** The prompt for the `/chat` endpoint must heavily constrain the LLM to only use the provided `ThoughtRecord` to prevent hallucinations.
- **Frontend:** New `CopilotSidebar` component, React Query hooks for fetching thoughts and sending chat messages.

## 5. Scope & Future Considerations
This design strictly covers the foundational `ThoughtRecord` pipeline, the visual widget rendering, and the LLM chat/injection layer. Future phases could introduce multi-agent debate visualization or deep historical backtest interrogation using the same data model.
