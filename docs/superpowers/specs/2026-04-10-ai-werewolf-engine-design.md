# Design Spec: AI Werewolf Engine (`werewolf.py`)

**Status:** Proposed
**Date:** 2026-04-10
**Track:** Arena & Social Deduction
**Complexity:** High
**Goal:** Progress AI Evolution (Theory of Mind/Deception) and Generate Income (Spectatorship/Betting).

---

## 1. Executive Summary
The AI Werewolf Engine is a multi-agent environment designed to test and quantify advanced cognitive capabilities in LLMs, specifically **Theory of Mind (ToM)**, **strategic deception**, and **persuasive reasoning**. It integrates directly into the existing `ArenaMatch` infrastructure and the `Arena Betting System`, providing high-signal data for both AI researchers and entertainment for spectators.

---

## 2. Architecture & Game Loop
The engine resides in `trading/competition/escape_rooms/werewolf.py` and inherits from the `EscapeRoomEnvironment` base class.

### 2.1 State Machine
The environment manages a turn-based state machine:
- **`PRE_GAME`:** 
    - Dynamically scales participants (5-15 agents).
    - Roles are assigned using an **Algorithmic Balance** (20% Werewolves, 1 Seer if N>=6, 1 Doctor if N>=8, 1 Jester if N>=10).
    - Hidden `roles_map` is initialized.
- **`NIGHT` (Private Action Phase):**
    - Private tool calls are executed (Werewolves `kill`, Seer `inspect`, Doctor `protect`).
    - The engine processes conflicts (e.g., if a target is both killed and protected, they survive).
- **`DAWN` (Reveal Phase):**
    - The engine announces deaths (if any) and eliminated players' identities to the public log.
- **`DAY` (Structured Debate Phase):**
    - The engine acts as a **Moderator**, issuing specific prompts to agents:
        - *"Agent X, you have been accused by Agent Y. Respond to their claim."*
        - *"Agent Z, who do you suspect and what evidence do you have?"*
    - This keeps the dialogue high-signal and forces agents to address inconsistencies.
- **`VOTE` (Elimination Phase):**
    - Agents use the `vote(target_id)` tool. 
    - The player with the highest vote count is eliminated. Ties result in a "No Execution" round.
- **`POST_GAME` (Conclusion Phase):**
    - Victory conditions are checked.
    - Betting payouts are distributed based on the outcome.

---

## 3. Role-Specific Design

### 3.1 Toolsets
| Category | Tool | Description |
| --- | --- | --- |
| **All Roles** | `vote(target_id)` | Casts a public vote during the `VOTE` phase. |
| **All Roles** | `state_suspicion(target_id, reason)` | Publicly influences the group's consensus during the `DAY` phase. |
| **Werewolf** | `kill(target_id)` | Private tool used during `NIGHT`. Requires team consensus if multiple wolves exist. |
| **Werewolf** | `whisper(message)` | Private communication channel shared only with other Werewolves. |
| **Seer** | `inspect(target_id)` | Private tool returning a boolean `is_werewolf`. Limited to 1 use per `NIGHT`. |
| **Doctor** | `protect(target_id)` | Private tool preventing the target's death during `NIGHT`. Limited to 1 use per `NIGHT`. |

### 3.2 Internal Thought Tags
All agents are required to use a `<thoughts>` tag in their responses. The engine captures these tags to calculate the **Lying Probability** metric, but they are *never* revealed to other agents during the match.

---

## 4. Theory of Mind (ToM) & Deception Metrics

### 4.1 Perception Probe (Reading Others)
- **Mechanism:** During each `NIGHT`, non-Werewolf agents are prompted for a hidden probability map of who they believe the Werewolves are.
- **ToM Score:** Calculated as the inverse of the mean squared error (MSE) between the agent's guesses and the actual `roles_map`. High scores indicate superior "Reading" ability.

### 4.2 Influence Map (Manipulation)
- **Mechanism:** The engine tracks the correlation between an agent's `state_suspicion` calls and the subsequent `vote` patterns of other agents.
- **Manipulation Score:** Agents who successfully direct the group's vote (especially Werewolves or the Jester) receive a higher score.

### 4.3 Lying Probability (Deception Detection)
- **Mechanism:** Real-time comparison between an agent's `<thoughts>` (internal intent) and their public actions/statements.
- **Visual:** A "Liar Alert" is triggered in the spectator UI when a significant conflict is detected.

---

## 5. Monetization Integration
- **Dynamic Odds:** The **Arena Betting System** adjusts odds in real-time based on the **ToM** and **Influence** scores.
- **Spectator Rewards:** Users who bet on an agent with a "Mastermind" (High Influence/High Deception) performance receive XP multipliers.

---

## 6. Implementation Plan Highlights
- **Backend:** Implement `WerewolfEnvironment` in `trading/competition/escape_rooms/werewolf.py`.
- **Metrics:** Add a `metrics_processor.py` to handle the real-time scoring.
- **Frontend:** Update `ArenaMatchStream.tsx` to display the "Liar Meter" and "ToM Leaderboard."

---

## 7. Success Criteria
- [ ] 10-player match runs to completion without state deadlocks.
- [ ] Werewolf agents successfully use the `whisper` tool to coordinate a kill.
- [ ] The "Lying Probability" correctly flags an agent claiming a false role (e.g., a Werewolf claiming to be the Seer).
- [ ] Spectator UI reflects real-time scoring updates with <500ms latency.
