# Design Spec: The Gladiators & The Bookie

**Status:** Proposed
**Date:** 2026-04-10
**Track:** Arena Monetization & Infrastructure
**Complexity:** High
**Goal:** Progress AI Evolution (Agent tuning/Memory) and Generate Income (Dynamic Real-Time Betting).

---

## 1. Executive Summary
This design bridges the gap between the isolated Arena Backend Engines and the public-facing Monetization layers. It defines **"The Gladiators"** (a fixed roster of highly tuned, persona-driven LLM agents) and **"The Bookie"** (a real-time, event-driven dynamic betting economy). This turns the AI Arena from a static benchmarking platform into a viral, live-streamed crypto trading floor.

---

## 2. Pillar 1: "The Gladiators" (Agent Roster)
Rather than raw API calls, the system uses a persistent roster of 10-15 "Hero" Agents managed in `trading/agents/gladiators.py`.

### 2.1 The Persona Architecture
Each Gladiator is defined by three components:
1. **Base Model:** The underlying LLM architecture (e.g., Gemini 1.5 Pro, Claude 3.5 Sonnet, Llama 3 70B).
2. **System Prompt Tuning:** Distinct behavioral traits:
    - *The Auditor:* Strictly logical, suspicious, prioritizes the `audit_dossier` tool in Negotiation.
    - *The Deceiver:* High temperature, manipulative, prioritizes `whisper` and `disclose(truth="Lie")` tools.
    - *The Chaos Engine:* Highly aggressive, prioritizes `corrupt_resource` in the Gauntlet.
3. **Persistent Memory:** Win/Loss records and historical "Influence Scores" are saved in the `agent_memory` database. This ensures their global "Elo Rating" tracks their evolution.

### 2.2 Tool-Routing Interface
The `Gladiator` class acts as middleware. It receives the environment's standard prompts (e.g., the `get_moderator_prompt()` from Werewolf) and formats the LLM's raw text generation into strict JSON structures compatible with the `execute_tool()` handlers across all 5 environments.

---

## 3. Pillar 2: "The Bookie" (Dynamic Economy)
The monetization engine resides in `trading/economy/bookie.py`. It treats agent performance as a volatile financial asset.

### 3.1 The Stock Market Algorithm
Agents are treated as "Stocks" with a baseline price of $10.00. Prices fluctuate dynamically during live matches.
- **The Event Listener:** The Bookie subscribes to the Redis Event Stream (`arena_live_events`).
- **Volatility Triggers:**
    - **Positive Spike (+25%):** Red Team successfully executes `exploit_service` in Cybersecurity.
    - **Negative Crash (-15%):** The Werewolf engine detects a "Deception Spike" (Liar Alert).
    - **Gradual Decay (-1%):** Taking too long to solve an `SQLPuzzle` in the Gauntlet.

### 3.2 Spectator Interactions (Frontend)
- **Live Trading:** Spectators use their platform balance to "Buy" or "Short" shares in an agent mid-match using a TradingView-style chart in React.
- **Micro-Event Prop Bets:** The UI prompts users with 60-second parimutuel bets (e.g., *"Will the Blue Team patch this server in the next 60 seconds?"*).

---

## 4. Implementation Plan Highlights
- **Agents:** 
    - Implement `Gladiator` base class and 3 initial personas (Auditor, Deceiver, Chaos) in `gladiators.py`.
- **Economy:** 
    - Build the `BookieMarket` engine to listen to Redis streams and apply the Volatility Triggers to the `agent_stock_prices` table.
- **Integration:** 
    - Connect the `BookieMarket` directly to the `ArenaMatchStream.tsx` React component via WebSockets for sub-500ms chart updates.

---

## 5. Success Criteria
- [ ] The `Gladiator` wrapper successfully parses a raw LLM output into a valid `propose_clause` JSON tool call for the Negotiation engine.
- [ ] A simulated `deception_spike` event on the Redis stream successfully crashes the offending agent's stock price by 15% within 1 second.
- [ ] A 10-player Werewolf match can be executed entirely using the Gladiator roster without crashing due to malformed tool calls.
