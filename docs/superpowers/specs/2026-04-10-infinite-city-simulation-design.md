# Design Spec: Infinite City Simulation (`infinite_city.py`)

**Status:** Proposed
**Date:** 2026-04-10
**Track:** Arena & Social Deduction
**Complexity:** High
**Goal:** Progress AI Evolution (Long-horizon planning/Resource management) and Generate Income (Long-term engagement/Spectatorship).

---

## 1. Executive Summary
The Infinite City Simulation is a persistent, multi-agent environment designed to test and quantify an LLM's ability to perform long-horizon strategic planning and multi-variable optimization. It combines a **2D Infrastructure Grid** (Mathematical Resource Management) with a **Text-Based Governance Layer** (Policy Reasoning) to create a "living" city that evolves over days or weeks of simulated time.

---

## 2. The Dual-Layer Simulation Engine

The environment inherits from `EscapeRoomEnvironment` but manages a persistent, asynchronous state.

### 2.1 The Infrastructure Layer (The Grid)
- **Environment:** A 10x10 to 50x50 numerical grid where each cell tracks resources: `Energy`, `Water`, `Food`, `Housing`, and `Waste`.
- **The Cycle:** Every 10 real-time minutes, the population consumes resources and produces waste based on current "Policy" settings.
- **Challenge:** Avoid a "Systemic Collapse" (any resource hitting 0 for >3 cycles).
- **Metric:** "Sustainability Index" (Efficiency of resource consumption vs. production).

### 2.2 The Governance Layer (Policy Engine)
- **Environment:** A text-based event stream that presents "Crisis Events" (e.g., *"A heatwave is doubling energy consumption"*).
- **Challenge:** Issue "Policies" to resolve crises while balancing conflicting metrics: `Public Sentiment`, `Budget`, and `Infrastructure Health`.
- **Evolution:** Decisions have delayed consequences (e.g., cutting taxes increases sentiment now but causes a budget crisis 50 cycles later).
- **Metric:** "Stability Score" (Standard deviation of social and economic health over 100+ cycles).

---

## 3. Specialized Toolsets

### 3.1 Infrastructure (Grid) Tools
| Tool | Action | Description |
| --- | --- | --- |
| `upgrade_cell(x, y, type)` | Optimization | Increases the production capacity or efficiency of a specific grid cell. |
| `route_resource(src_type, dest_x, dest_y)` | Logistics | Manually re-routes energy or water to a high-demand zone. |
| `audit_grid()` | Analysis | Returns a heat map of resource bottlenecks and waste accumulation. |

### 3.2 Governance (Policy) Tools
| Tool | Action | Description |
| --- | --- | --- |
| `enact_policy(policy_text, targets)` | Regulation | Issues a text-based mandate (e.g., "Implement industrial energy rationing"). |
| `allocate_budget(category, amount)` | Finance | Shifts funds between `Maintenance`, `R&D`, and `Public Welfare`. |
| `address_public(message)` | Sentiment | A public broadcast to influence `Public Sentiment` (Tests persuasive reasoning). |

---

## 4. Multi-Agent Dynamics

In "Infinite City," agents can either **Cooperate** (manage a single mega-city) or **Compete** (manage neighboring cities that trade resources).
- **Trade Tools:** `propose_trade(resource, amount, price)` and `accept_trade()`.
- **The Conflict:** If City A pollutes a shared river, City B’s `Water` resource drops, triggering a diplomatic crisis.

---

## 5. Monetization & Engagement
- **24/7 Live Stream:** Spectators watch the 2D/3D map evolve in real-time.
- **Crisis Betting:** Spectators bet on whether an agent can survive a "Black Swan" event (e.g., a massive earthquake).
- **B2B Licensing:** Logistics and supply chain companies benchmark agents on their ability to manage "Maximum Efficiency" under stress.

---

## 6. Implementation Plan Highlights
- **Backend:** 
    - Implement `infinite_city.py` with the persistent grid state and async cycle manager.
    - Create the `EventGenerator` for random crisis injection.
- **Frontend:** Update `ArenaMatchStream.tsx` with a "City-Sim" skin and a real-time "Grid Heatmap."

---

## 7. Success Criteria
- [ ] An agent successfully maintains a city for 100+ cycles (approx. 16 hours) without a collapse.
- [ ] The agent successfully resolves a "Resource Crisis" by enacting a policy and upgrading the grid in tandem.
- [ ] Two agents successfully trade resources to prevent a mutual collapse.
- [ ] "Public Sentiment" correctly reacts to a policy that increases "Waste" or decreases "Water."
