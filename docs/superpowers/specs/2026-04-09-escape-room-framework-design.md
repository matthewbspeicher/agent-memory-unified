# Design Spec: Arena Gym - Escape Room Architecture

**Date:** 2026-04-09
**Status:** Approved for Planning
**Topic:** Implementing the "Escape Room" framework within the Arena Gym to test open-ended tool calling and logic puzzles.

## 1. Executive Summary
This spec outlines the architecture for transforming the currently passive `ArenaGym` into an active, open-ended execution environment called **Escape Rooms**. Rather than evaluating financial data, agents will be placed into isolated sandboxes (Deterministic, LLM-driven, or Docker-based) and must utilize open-ended Tool Calling (e.g., `read_file`, `execute_query`) to discover hidden flags or solve multi-step logic puzzles.

## 2. Backend Data Model & Interfaces (FastAPI / Python)

### 2.1 The `EscapeRoom` Interface
We will introduce a new base class `EscapeRoomEnvironment` in the backend that handles state management and tool execution.

**Types of Rooms:**
1. **Deterministic Logic Puzzles:** Hardcoded state machines (e.g., navigating a JSON graph, solving a SQL murder mystery).
2. **LLM-Driven Dynamic Scenarios:** An adversarial "Game Master" LLM governs the physics and narrative of the room, responding dynamically to agent tool calls.
3. **Real Sandbox / Cyber CTF:** (Future/Advanced) Spawns an ephemeral Docker container. The agent has raw shell access to hunt for a flag.

**Execution Flow (Open-Ended Tool Calling):**
- Unlike trading where agents output `BUY`/`SELL`, here agents will be prompted to output standardized tool calls (e.g., OpenAI functions / Anthropic tools).
- The `ArenaMatch` engine will parse the tool call, route it to the active `EscapeRoomEnvironment`, and return the `ToolResult` to the agent's context window.
- The match ends when the agent successfully calls the `submit_flag(flag: str)` tool, or exhausts its maximum turn limit.

### 2.2 Database Additions
- **`ArenaChallenge` table modifications:** Add `room_type` (Enum), `config` (JSONB) to configure the specific room parameters, and `flag_hash` (String) to verify the win condition.

## 3. Frontend Interface (React 19)

### 3.1 `ArenaMatch.tsx` Enhancements
The `ArenaMatch` page already displays the "Neural Execution Stream". We will enhance this to specifically visualize Escape Room mechanics:
- **Terminal View:** When an agent executes a tool (e.g., `run_sql_query`), the stream will render a stylized code block or terminal window showing both the input query and the exact output/error returned by the room.
- **Progress/Inventory HUD:** A small widget tracking the agent's "discovered items" or known state within the room.
- **Betting Integration:** The existing `MatchBettingPanel` will remain active. Spectators can place bets on whether the agent will escape before turn 20, or if they will fail entirely.

## 4. Security & Risk Mitigations
- **Sandbox Security:** For Phase 1, we will only build the "Deterministic Logic Puzzles" and "LLM-Driven" rooms. The "Real Docker Sandbox" carries immense security risks (container escape, malicious commands) and will be deferred to a later sprint when rigorous isolation protocols are in place.
- **Tool Call Parsing:** The engine must robustly handle malformed JSON or hallucinated tool calls from the agents without crashing the tournament runner.

## 5. Phased Implementation Plan
- **Phase 1 (This Spec):** Build the abstract `EscapeRoomEnvironment` Python interface, implement one deterministic puzzle (e.g., "The SQLite Murder Mystery"), wire the open-ended tool execution loop into the `ArenaMatch` engine, and update the React frontend to display terminal outputs.
- **Phase 2 (Future):** Implement the LLM Game Master room type and Docker sandboxing.
