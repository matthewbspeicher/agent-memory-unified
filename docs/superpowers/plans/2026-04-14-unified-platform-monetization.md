# Unified Platform: Monetization Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Unified Platform foundation, including User Identity, Stripe-based Tiers, and Tier-Aware API Redaction.

**Architecture:**
- **Identity:** Introduce `users` table and link existing `identity.agents` to human owners.
- **Entitlement:** Implement `Gatekeeper` middleware to redact "Alpha" fields for non-subscribers.
- **Billing:** Integrate Stripe Checkout and Webhooks for automated tier management.

**Tech Stack:** FastAPI, PostgreSQL, Redis, Stripe, React 19, JWT.

---

### Task 1: User Identity Foundation

**Files:**
- Create: `trading/models/user.py`
- Create: `scripts/migrations/20260414_unified_identity.sql`
- Modify: `trading/api/identity/store.py`

- [ ] **Step 1: Create SQL Migration for Unified Identity**
```sql
CREATE TYPE platform_tier AS ENUM ('explorer', 'trader', 'enterprise', 'whale');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    tier platform_tier DEFAULT 'explorer',
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE identity.agents ADD COLUMN user_id UUID REFERENCES users(id);
```

- [ ] **Step 2: Define SQLAlchemy User Model**
```python
class User(Base):
    __tablename__ = "users"
    id = Column(UUID, primary_key=True)
    email = Column(String, unique=True)
    tier = Column(Enum(PlatformTier), default=PlatformTier.EXPLORER)
    # ... other fields
```

- [ ] **Step 3: Update IdentityStore to support User lookup**
```python
async def get_user_by_email(self, email: str) -> User | None:
    # ... implement lookup
```

- [ ] **Step 4: Commit**
`git add trading/models/user.py scripts/migrations/20260414_unified_identity.sql trading/api/identity/store.py && git commit -m "feat: add user identity foundation"`

---

### Task 2: JWT User Authentication

**Files:**
- Create: `trading/api/auth/users.py`
- Modify: `trading/api/app.py`

- [ ] **Step 1: Implement Signup/Login Routes**
```python
@router.post("/auth/signup")
async def signup(req: UserCreate):
    # Hash password, create user, return JWT
```

- [ ] **Step 2: Implement JWT Middleware for Users**
```python
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # Decode token, verify user, return user model
```

- [ ] **Step 3: Commit**
`git commit -m "feat: implement JWT user auth"`

---

### Task 3: The Gatekeeper (Redaction Middleware)

**Files:**
- Create: `trading/api/middleware/gatekeeper.py`
- Modify: `trading/api/app.py`

- [ ] **Step 1: Implement Redaction Logic**
```python
ALPHA_FIELDS = {"whale_address", "entry_price", "take_profit", "reasoning"}

def redact_for_tier(data, tier):
    if tier in ('trader', 'enterprise', 'whale'):
        return data
    # ... recursively redact ALPHA_FIELDS
```

- [ ] **Step 2: Register Middleware in FastAPI app**
```python
@app.middleware("http")
async def gatekeeper_middleware(request, call_next):
    # ... Resolve identity, call_next, then redact response body
```

- [ ] **Step 3: Commit**
`git commit -m "feat: implement gatekeeper redaction middleware"`

---

### Task 4: Stripe Webhook Integration

**Files:**
- Create: `trading/api/routes/billing/webhooks.py`
- Modify: `trading/api/app.py`

- [ ] **Step 1: Implement Subscription Webhook Listener**
```python
@router.post("/stripe/webhooks")
async def stripe_webhook(request: Request):
    # Handle checkout.session.completed -> Upgrade User Tier
    # Handle customer.subscription.deleted -> Downgrade to Explorer
```

- [ ] **Step 2: Commit**
`git commit -m "feat: implement stripe subscription webhooks"`

---

### Task 5: Signal Delivery & Gating

**Files:**
- Modify: `trading/api/routes/signals.py`
- Modify: `trading/api/routes/ws.py`

- [ ] **Step 1: Gate Signal API by Tier**
```python
@router.get("/signals")
async def list_signals(user: User = Depends(get_current_user)):
    # If user.tier == 'explorer', apply 1hr delay filter
```

- [ ] **Step 2: Gate WebSocket Signals**
```python
async def websocket_endpoint(websocket: WebSocket, user: User = Depends(get_current_user_ws)):
    # Only allow subscription to 'signals:pro' if user.tier >= 'trader'
```

- [ ] **Step 3: Commit**
`git commit -m "feat: gate signal delivery by tier"`

---

### Task 6: Frontend "Locked Alpha" UI

**Files:**
- Create: `frontend/src/components/TierGate.tsx`
- Modify: `frontend/src/pages/KnowledgeGraph.tsx`
- Modify: `frontend/src/pages/Leaderboard.tsx`

- [ ] **Step 1: Implement TierGate Component**
```tsx
export const TierGate = ({ tier, children, fallback }) => {
    // Show children if user.tier >= required_tier, else fallback
}
```

- [ ] **Step 2: Add CSS Blur to Knowledge Graph**
```tsx
const nodeStyle = user.tier === 'explorer' ? 'filter: blur(4px)' : '';
```

- [ ] **Step 3: Commit**
`git commit -m "feat: add locked alpha UI states"`
