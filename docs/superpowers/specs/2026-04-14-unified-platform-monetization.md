# Unified Specification: Agent Memory Unified Platform (Monetization Phase 1)

**Status:** Proposed (Supersedes 2026-04-14-alpha-terminal, 2026-04-14-signal-api, 2026-04-14-agent-auth-api)
**Date:** 2026-04-14
**Topic:** Consolidating Identity, Signal API, and Terminal Monetization into a Unified Subscription Platform.

---

## 1. Executive Summary
Transform the Agent Memory platform into a unified B2C/B2B intelligence service. We provide three distinct value propositions under a single subscription:
1.  **Alpha Terminal:** Dashboard + WebSocket Copy-Trading + 3D Knowledge Graph.
2.  **Signal API:** REST API signals + Webhooks for automated systems.
3.  **Agent Auth API:** Enterprise-grade identity as a service for AI agents.

This unified platform introduces a **User-Centric Identity Model** where one User (Human or Org) owns many Agents/API Keys, all governed by a single billing tier.

---

## 2. Unified Tier Structure

| Tier | Price | Audience | Terminal Access | Signal API | Auth API |
|------|-------|----------|-----------------|------------|----------|
| **Explorer** | $0 | Casuals | 1hr Delay, Blurred KG | 100 req/day (Delayed) | 5 Agents |
| **Trader** | $49/mo | Retail Traders | Real-time, Full KG | 10,000 req/day | 50 Agents |
| **Enterprise**| $199/mo | Algo/Funds | Real-time + Custom Views | 100,000 req/day + Webhooks | Unlimited |
| **Whale** | Custom | Partners | Custom Dashboard | Unlimited Quotas | Custom Scopes |

### 2.1 Entitlement Enforcement
- **Explorer:** API redact "alpha" fields (e.g., `whale_address`, `entry_price`). UI blurs Knowledge Graph. 15-min - 1hr delay.
- **Trader:** Full real-time access. WebSocket copy-trading enabled.
- **Enterprise:** Reasoning text included in signals. Full audit logging (last 30 days). Webhook delivery.

---

## 3. Architecture: The "Platform Core"

### 3.1 Identity & User Authentication (PREREQUISITE)
We will introduce a `User` entity to bridge the gap between human owners and automated agents.
- **User Identity:** Email/Wallet based signup.
- **Agent Identity:** Managed under a User account. Existing `identity.agents` table will be linked to `users.id`.
- **JWT Auth:** Users authenticate via JWT (using `amu_user_xxx.yyy`). Agents authenticate via existing `amu_agent_xxx.yyy` tokens.

### 3.2 The Gatekeeper (Redaction Middleware)
A new FastAPI middleware (`api/middleware/gatekeeper.py`) will implement **Tier-Aware Redaction**.
- It checks `user.tier` for the current identity.
- It applies `redact_alpha_fields(data, tier)` to the JSON response body.
- **Locked Fields:** `whale_address`, `exact_entry`, `take_profit`, `reasoning` (Enterprise only).

### 3.3 Signal Delivery (Unified Hub)
- **REST:** Polling signals and opportunities via `api/routes/signals.py`.
- **WebSocket:** Real-time push for "Trader" tier via `api/routes/ws.py`.
- **Webhooks:** Instant notification for "Enterprise" tier via `api/routes/webhooks.py`.

---

## 4. Billing & Stripe Integration

### 4.1 Subscription Flow
1.  **Stripe Checkout:** Redirect users to a hosted checkout for the chosen tier.
2.  **Webhook Handler (`api/routes/billing/webhooks.py`):**
    - `checkout.session.completed` → Upgrade user to `Trader/Enterprise`.
    - `customer.subscription.deleted` → Downgrade to `Explorer`.
    - `invoice.payment_failed` → Mark tier as `grace_period` or `restricted`.

### 4.2 Crypto Tipping (Reputation)
- **Network:** Initially support **USDC on Polygon/Base** (low fees).
- **Verification:** Use Alchemy RPC to verify `tx_hash` before crediting reputation points to an agent.

---

## 5. Security & Rate Limiting
- **HMAC Signatures:** All signals (REST, WS, Webhooks) include `X-AMU-Signature` to prevent spoofing.
- **Redis Rate Limiting:** Track usage per `user_id` or `api_key` using Redis window-based counters (already partially implemented in `limiter.py`).

---

## 6. Data Model (Unified Schema)

### 6.1 `users` (New)
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'explorer',
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 6.2 `identity.agents` (Extend)
```sql
ALTER TABLE identity.agents ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE identity.agents ADD COLUMN tier TEXT; -- Redundant but cached for speed
```

### 6.3 `usage_logs` (New)
```sql
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    resource TEXT NOT NULL, -- 'signal_api', 'terminal_ws', etc.
    request_count INTEGER DEFAULT 1,
    period_start TIMESTAMPTZ NOT NULL,
    UNIQUE(user_id, resource, period_start)
);
```

---

## 7. Implementation Strategy: Order of Operations

1.  **Foundation:** Implement `User` model, Signup/Login, and link `identity.agents` to `users`.
2.  **Entitlement:** Build the `Gatekeeper` middleware and the field redaction logic.
3.  **Billing:** Integrate Stripe Checkout and webhook lifecycle handlers.
4.  **UI/UX:** Add "Locked Alpha" blurred states and the "Follow Agent" Signal modal.
5.  **Signals:** Implement the `signals:pro` Redis stream and WebSocket subscription gating.
6.  **Enterprise:** Build the Webhook delivery system and "Reasoning" field exposure.
7.  **Phase 2:** Crypto Tipping and Reputation Boosts.

---

## 8. Spec Self-Review

1.  **Gap Check:** Addresses Identity system mismatch (User vs Agent). Defines Stripe flow. Sets explicit tier pricing.
2.  **Consistency:** Unified tier names (Explorer/Trader/Enterprise) used across all modules.
3.  **Clarity:** Explicit order of operations defined. Redaction logic clarified as API-level.
4.  **Security:** HMAC signatures and rate-limiting headers included.
