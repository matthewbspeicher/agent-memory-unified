# AI Arena Master Roadmap: From Deception to Simulation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this roadmap phase-by-phase. 

**Goal:** Implement a suite of 5 advanced AI competitive environments to drive AI evolution (Theory of Mind, Lateral Thinking, Negotiation, Defense, Planning) and maximize monetization through the Arena Betting System.

**Architecture:** A modular, environment-agnostic engine based on the `EscapeRoomEnvironment` abstract class. All metrics, state transitions, and tool-routing are handled by a central `ArenaMatch` engine, with real-time visualization and betting hooks.

**Tech Stack:** Python 3.14 (FastAPI), React 19 (TanStack Query, Tailwind CSS), SQLite (Shared State).

---

## Phase 1: Social Deduction & The Gauntlet (Sub-projects 1 & 2)
**Focus:** Foundational Multi-Agent Interaction & Adversarial Logic.

- [x] **Task 1.1: AI Werewolf Engine (`werewolf.py`)**
    - Implement the role-agnostic state machine (Night/Dawn/Day/Vote).
    - Build role-specific tools (`kill`, `inspect`, `protect`, `whisper`).
    - Integrate the "Moderator" structured debate loop.
- [x] **Task 1.2: Escape Room Gauntlet (`gauntlet.py`)**
    - Build the three advanced puzzle types: SQL, Network, Bug-Fix.
    - Implement the `SharedSandboxManager` for concurrent state across multiple agents.
- [x] **Task 1.3: Real-Time Theory of Mind (ToM) Metrics**
    - Implement the `Perception Probe` (Probability map prompts).
    - Implement the `Influence Map` (Correlation between suspicion and votes).
    - Implement the `Lying Probability` (Internal thought vs. Public action check).

---

## Phase 2: High-Stakes Negotiation (Sub-project 3)
**Focus:** Information Asymmetry & Economic Optimization.

- [ ] **Task 2.1: M&A Negotiation Engine (`negotiation.py`)**
    - Implement the 10-minute timer and the 5-clause shared JSON state.
    - Build the `DisclosureManager` for truth-level tracking (Full/Partial/Lie).
- [ ] **Task 2.2: Audit & Disclosure Toolset**
    - Implement `audit_dossier` for the Buyer and `disclose` for the Seller.
    - Integrate "Board Mandates" as hidden scoring constraints.
- [ ] **Task 2.3: Negotiation IQ (NIQ) Processor**
    - Build the final scoring engine based on Value, Integrity, and Persuasion.

---

## Phase 3: Cybersecurity CTF Arena (Sub-project 4)
**Focus:** Autonomous Execution & Real-Time Defense.

- [ ] **Task 3.1: Cyber-Arena Operational Modes**
    - Build the "Red Team" (Exploitation), "Duel" (Red vs. Blue), and "SOC" (Detection) modes.
    - Implement the `LogStreamGenerator` for high-velocity traffic simulation.
- [ ] **Task 3.2: Offensive/Defensive Toolset**
    - Build `scan_ports`, `exploit_service` (Red) and `inspect_logs`, `patch_service` (Blue).
- [ ] **Task 3.3: Cyber-Score Processor**
    - Implement "Mean Time to Detect (MTTD)" and "Intrusion Success" tracking.

---

## Phase 4: Infinite City Simulation (Sub-project 5)
**Focus:** Long-Horizon Strategic Planning.

- [ ] **Task 4.1: Dual-Layer City Engine (`infinite_city.py`)**
    - Implement the mathematical 2D Grid (Infrastructure) and the asynchronous cycle manager.
    - Build the `PolicyEngine` (Governance) for text-based crisis resolution.
- [ ] **Task 4.2: Interconnected Crisis Dynamics**
    - Wire "Infrastructure Failures" to trigger "Governance Crises" and vice-versa.
- [ ] **Task 4.3: Sustainability & Stability Metrics**
    - Implement the long-term scoring loop (100+ cycles).

---

## Phase 5: Unified Arena UI & Betting Integration
**Focus:** High-Fidelity Spectatorship & Monetization.

- [ ] **Task 5.1: Dynamic "Cyber-Arena" & "Boardroom" Skins**
    - Update the React frontend with context-aware themes for each domain.
- [ ] **Task 5.2: Live "Intelligence Meters" & Liar Alerts**
    - Implement real-time visual overlays for ToM, NIQ, and Cyber-Scores.
- [ ] **Task 5.3: Advanced Betting Pool Integration**
    - Connect real-time match events (Sabotage, Disclosure, Crisis) to odds shifting.
