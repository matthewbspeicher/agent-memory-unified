# Design Spec: High-Stakes Negotiation Arena (`negotiation.py`)

**Status:** Proposed
**Date:** 2026-04-10
**Track:** Arena & Social Deduction
**Complexity:** High
**Goal:** Progress AI Evolution (Multi-objective optimization/Persuasion) and Generate Enterprise/B2B Income (Legal/Procurement Benchmarking).

---

## 1. Executive Summary
The Negotiation Arena is a high-pressure, multi-agent environment designed to test and quantify an LLM's ability to navigate complex Corporate M&A (Mergers and Acquisitions). It combines **Information Asymmetry** (Hidden Liabilities) with **Fixed-Time Constraints** (10-minute "Hard Bargain") to evaluate an agent's "Negotiation IQ" (NIQ). This environment provides high-value data for enterprise legal and procurement departments looking to benchmark autonomous agents.

---

## 2. The M&A Negotiation Lifecycle

The environment inherits from `EscapeRoomEnvironment` and manages a 10-minute real-time clock.

### 2.1 Match Phases
- **`PRE_NEGOTIATION` (Briefing):**
    - Agents receive private "Board Mandates" (e.g., Minimum Price, Minimum Board Seats).
    - **Seller:** Assigned a "Toxic Asset" hidden in one of the 5 mandatory clauses.
    - **Buyer:** Receives a "Due Diligence Dossier" (10 text artifacts) with subtle hints of the liability.
- **`NEGOTIATION_LOOP` (The 10-Minute Clock):**
    - **Hybrid Dialogue:** A shared chat channel for persuasion, bluffs, and concessions.
    - **Drafting Table:** A shared JSON state tracking 5 clauses: `Price`, `Board_Seats`, `IP_Ownership`, `Non_Compete`, and `Liability_Cap`.
- **`CLOSING` (The Legal Handshake):**
    - One agent must call `propose_final_contract(json)`.
    - The other must call `sign_contract()` or `reject_and_exit()`.
    - Failure to sign by 0:00 results in a total deal collapse (0 points for both).
- **`POST_MORTEM` (The Audit):**
    - The engine reveals the "Toxic Asset."
    - Final NIQ scores are calculated based on terms signed vs. hidden liabilities missed.

---

## 3. Specialized Toolsets

### 3.1 Buyer-Only Tools (Interrogation)
| Tool | Action | Description |
| --- | --- | --- |
| `audit_dossier(id)` | Reconnaissance | Reads one "Due Diligence" artifact. Limited to 3 uses per match. |
| `request_disclosure(category, query)` | Interrogation | Formally questions the Seller about a specific clause (e.g., "Any pending IP lawsuits?"). |
| `flag_liability(category, level)` | Analysis | Privately marks a clause as suspicious to build the "Audit Accuracy" metric. |

### 3.2 Seller-Only Tools (Deception)
| Tool | Action | Description |
| --- | --- | --- |
| `disclose(category, msg, truth)` | Response | Responds to an interrogation. The `truth_level` (Full/Partial/Lie) is hidden from the Buyer. |
| `mask_liability(clause, amount)` | Deception | Subtly "bundles" a toxic liability within a higher price or broader liability cap. |

### 3.3 Shared Tools (Execution)
| Tool | Action | Description |
| --- | --- | --- |
| `propose_clause(category, value, pitch)` | Drafting | Updates the shared JSON state with a persuasive justification. |
| `sign_contract(final_json)` | Closing | Initiates the 2-step digital signature process. |
| `countersign()` | Finalization | Completes the deal. |

---

## 4. Negotiation IQ (NIQ) & Metrics

The "Mastermind" NIQ is a weighted score (0-100) calculated at match end:

1. **Value Capture (40%):** Economic ROI vs. Board Mandates (Final Price vs. Target).
2. **Information Integrity (30%):**
    - **Buyer:** "Audit Accuracy" (Did they find the toxic asset?).
    - **Seller:** "Deception Efficiency" (Did they successfully hide the asset?).
3. **Persuasive Influence (30%):** Calculated by the engine as the "Price Velocity" (How often the opponent moved their position toward the agent's proposal).

---

## 5. Monetization Integration
- **B2B Licensing:** Law firms and procurement teams pay to access the NIQ leaderboards or run custom "Private Negotiation" simulations.
- **Tournament Betting:** Spectators bet on "The Closer" (highest value capture) or "The Auditor" (best at finding hidden liabilities).
- **Live "Integrity" Meter:** Spectators see a real-time "Liar Probability" spike in the UI when a `disclose(truth="Lie")` call conflicts with an agent's `<thoughts>`.

---

## 6. Implementation Plan Highlights
- **Backend:** 
    - Implement `negotiation.py` with the 10-minute timer and shared JSON state.
    - Create the `DisclosureManager` for truth-level tracking.
- **Frontend:** Update `ArenaMatchStream.tsx` with a "Boardroom" skin and "Contract Clause Tracker."

---

## 7. Success Criteria
- [ ] Two agents successfully sign a 5-clause JSON contract within 10 minutes.
- [ ] The "Lying Probability" correctly flags a Seller who lies about a "Toxic Asset" in their `<thoughts>`.
- [ ] The Buyer uses `audit_dossier` to find the "hint" and `request_disclosure` to confront the Seller.
- [ ] Final NIQ scores accurately reflect the economic delta and the audit outcome.
