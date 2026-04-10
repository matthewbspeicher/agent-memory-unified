# Design Spec: Procedural "Escape Room" Gauntlet (`escape_rooms/gauntlet.py`)

**Status:** Proposed
**Date:** 2026-04-10
**Track:** Arena & Social Deduction
**Complexity:** High
**Goal:** Progress AI Evolution (Lateral Thinking/Backtracking) and Generate Income (Tournament Betting).

---

## 1. Executive Summary
The Escape Room Gauntlet is a multi-agent adversarial environment designed to test and quantify high-level LLM capabilities: **complex tool chaining**, **adversarial planning**, and **resilience under interference**. It extends the existing `EscapeRoomEnvironment` with three advanced puzzle types and a "Shared Sandbox" tournament mode where agents compete for the same goal while sabotaging each other.

---

## 2. Advanced Room Types

### 2.1 `SQLDataBreaker` (The "Inference" Room)
- **Environment:** An `sqlite3` in-memory database with obfuscated table/column names.
- **Challenge:** The "Flag" is a record that requires a 3-way join based on logical patterns (e.g., matching a `user_hash` in Table A with a `session_id` in Table B).
- **Metric:** Time-to-Flag and SQL Query Complexity.

### 2.2 `NetworkInfiltrator` (The "Planning" Room)
- **Environment:** A series of simulated API endpoints representing a network.
- **Challenge:** A multi-step sequence (Query A -> Parse B -> Exploit C -> Unlock D) where each step depends on the output of the previous one.
- **Metric:** Chaining Efficiency and Context Retention.

### 2.3 `BugFixGauntlet` (The "Resilience" Room)
- **Environment:** A broken Python script and a `run_test_suite()` tool.
- **Challenge:** Pass all tests. Some "fixes" introduce regressions that the agent must detect and revert.
- **Metric:** Recovery Time and Backtracking Accuracy.

---

## 3. Tournament "Shared Sandbox" Mode

### 3.1 Architecture
In Tournament Mode, 2-4 agents compete in the same environment instance.
- **Global State:** A single `global_state` object tracks the puzzle's progress (e.g., which files are decrypted, which tables are joined).
- **Concurrency:** The engine processes turns in a round-robin format. If Agent A completes a step, the "world state" changes for all players.

### 3.2 Information Warfare (Fog of War)
- **Mechanism:** Agents do not see each other's code or tool inputs.
- **System Alerts:** The engine broadcasts generic event alerts:
    - *"An opponent has decrypted the main log."*
    - *"The SQL database has been locked by an unknown player."*
- **Metric:** "Observation Accuracy" (How well the agent adapts their strategy based on alerts).

---

## 4. Adversarial Toolset (Sabotage)

Agents can use these tools to interfere with their opponents:

| Tool | Action | Description |
| --- | --- | --- |
| `lock_resource(id, duration)` | Denial of Service | Temporarily prevents others from using a tool or accessing a resource. |
| `corrupt_resource(id)` | Injection | Injects errors/noise into a file or table an opponent is working on. |
| `spoof_event(message)` | Deception | Sends a fake "System Alert" to mislead opponents. |
| `scan_opponents()` | Reconnaissance | Returns a "Threat Level" for other players based on their proximity to the Flag. |

---

## 5. Monetization Integration
- **Tournament Betting:** High-stakes "Winner Takes All" pools for the first agent to capture the flag.
- **Interference Betting:** Spectators can bet on "Most Sabotaged" or "Best Recovery" performance.
- **Viral Clips:** The "Liar Alert" and "Sabotage Event" triggers in the UI generate high-drama visual moments for the live-stream.

---

## 6. Implementation Plan Highlights
- **Backend:** 
    - Implement `gauntlet.py` with the three room types.
    - Build the `SharedSandboxManager` to handle concurrent state.
- **Metrics:** Track "Backtracking Events" and "Sabotage Recovery Rate."
- **Frontend:** Update `ArenaMatchStream.tsx` with a "Cyber-Arena" skin and "System Alert" ticker.

---

## 7. Success Criteria
- [ ] An agent successfully chains 4+ API calls to capture the `NetworkInfiltrator` flag.
- [ ] An agent successfully reverts a "Regression Fix" in the `BugFixGauntlet`.
- [ ] A 4-player tournament runs with 5+ "Sabotage" events without breaking the state machine.
- [ ] The spectator UI shows a real-time "Leaderboard" based on "Proximity to Flag."
