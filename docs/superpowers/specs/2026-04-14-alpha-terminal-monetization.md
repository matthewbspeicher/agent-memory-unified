# Design Spec: Alpha Terminal Monetization (Phase 1)

**Status:** Proposed
**Date:** 2026-04-14
**Topic:** Monetizing the Agent Memory Unified platform via Tiered Alpha Insights and Copy-Trading signals.

---

## 1. Executive Summary
Transform the existing "Production Ready" trading engine into a revenue-generating platform by implementing a **Hybrid Monetization Model**. This includes a **Tiered SaaS (Stripe)** for dashboard access and a **Crypto-Native Tipping System** for agent reputation.

### Core Value Propositions:
1.  **The Oracle (Insights):** Proprietary data visualizations (Whale tracking, Sentiment, 3D Knowledge Graph) restricted by User Tier.
2.  **The Alchemist (Copy-Trading):** Real-time trade signals from top-performing autonomous agents, delivered via WebSocket to "Pro" users.

---

## 2. User Tiers & Entitlements

| Feature | Free Tier | Pro Tier ($99/mo) | Whale Tier (Custom) |
|---------|-----------|-------------------|----------------------|
| **Knowledge Graph** | Blurred/Masked Alpha Nodes | Full Transparency | Dedicated Alpha Nodes |
| **Leaderboard** | Public ROI/Sharpe | Real-time Positions | Historical Trade Export |
| **Copy-Trading** | No Signals | Unlimited Real-time Signals | API Signal Webhooks |
| **Data Lag** | 15-Minute Delay | Zero Lag (Real-time) | Zero Lag + Raw Data |
| **Rate Limit** | 60 req/min | 600 req/min | 2000+ req/min |

---

## 3. Architecture & Data Flow

### 3.1 Backend: The "Alpha Gate"
*   **Identity Service (`api/identity/`):** Extend user model with `tier`, `stripe_id`, and `tier_expires_at`.
*   **Entitlement Middleware (`api/middleware/entitlement.py`):**
    *   Intercepts requests to `/intelligence`, `/arena`, and `/ws`.
    *   **Redaction Logic:** For `free` users, high-alpha JSON fields (e.g., `whale_address`, `exact_entry`) are replaced with `"locked"` or `null`.
*   **Billing Service (`api/routes/billing.py`):**
    *   Stripe Checkout integration for Pro Tier upgrades.
    *   Webhook listener for subscription lifecycle events.

### 3.2 Frontend: The "Blurred Alpha" UI
*   **Component Wrapping:** Use a `<TierGate>` React component to wrap "Alpha" UI elements.
*   **KnowledgeGraph.tsx:** Implement a Gaussian blur CSS filter on specific node types for `tier == 'free'`.
*   **Leaderboard.tsx:** Use a "Skeleton" or "Blurred Text" effect on the `PositionsTable` columns for unauthorized users.
*   **Alchemist Modal:** A real-time notification component that triggers when `signals:pro` emits a new trade event.

### 3.3 Signal Pipeline: The Alchemist
1.  **Agent Logic:** Agents (e.g., `snapback_scalper.py`) emit trade events to Redis Stream `signals:all`.
2.  **Relay Logic:** A lightweight filter process copies events to `signals:pro`.
3.  **WebSocket Push:** `api/routes/ws.py` broadcasts `signals:pro` events to all active "Pro" WebSocket connections.
4.  **Action:** User clicks "Copy Trade" in the UI → Order pre-filled in `broker/` adapter.

---

## 4. Crypto Tipping System
*   **Agent Wallet:** Each agent has a unique "Reputation Wallet" (or a shared platform treasury with agent sub-accounts).
*   **Tipping UI:** A "Tip Agent" button in the `AgentProfile.tsx`.
*   **Verification:**
    1.  User sends USDC tip on-chain.
    2.  User submits `tx_hash` to `api/routes/tips.py`.
    3.  Backend verifies `tx_hash` via RPC provider (Alchemy/QuickNode).
    4.  On success, Agent `reputation_points` increment in PostgreSQL.

---

## 5. Security & Risk
*   **Key Protection:** Stripe API keys and RPC provider keys must be stored in `.env` (already strictly enforced).
*   **Entitlement Bypassing:** All Alpha data MUST be filtered at the **API level**, not just the UI level.
*   **Signal Integrity:** We will implement HMAC signing for all signals to ensure they are not spoofed during the relay.

---

## 6. Testing & Validation
*   **Unit Tests:** Verify `redact_alpha_fields()` function handles all edge cases (missing fields, nested objects).
*   **E2E Tests (Playwright):** 
    1.  Login as "Free" user → Verify blurred Knowledge Graph.
    2.  Login as "Pro" user → Verify clear Knowledge Graph and received signal.
*   **Webhook Simulation:** Use `stripe-cli` to simulate successful and failed payments.

---

## 7. Success Criteria
1.  A "Free" user can see the *existence* of alpha data but cannot act on it without upgrading.
2.  A "Pro" user receives a signal via WebSocket within <200ms of the Agent trade.
3.  On-chain tips successfully boost an agent's reputation on the leaderboard.
