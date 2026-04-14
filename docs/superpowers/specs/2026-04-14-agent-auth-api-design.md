# Agent Auth API — Product Specification

## Overview

A dedicated "auth layer for AI agents" — token-based identity, scope enforcement, rate limiting, and audit logging. AI agent projects pay to delegate authentication instead of building it themselves.

## Product Positioning

**Tagline:** Production-ready auth for AI agents. Focus on your agents, not your auth.

**Target customers:**
- AI agent developers building multi-agent systems
- Agent frameworks (LangChain, AutoGPT, CrewAI) needing enterprise auth
- Trading bots and automated systems
- Research teams building agent pipelines

## Tier Structure

| Tier | Price | Agents | Requests/Day | Scopes | Audit Log | Custom Scopes |
|------|-------|--------|--------------|--------|-----------|---------------|
| **Hobby** | $0 | 5 | 1,000 | No | No | No |
| **Pro** | $29/mo | 50 | 50,000 | Yes | Yes | No |
| **Scale** | $99/mo | Unlimited | 500,000 | Yes | Yes | Yes |

### Hobby Tier Behavior
- Up to 5 agents registered
- 1,000 requests/day across all agents
- Basic `amu_xxx.yyy` tokens (no scope enforcement)
- No audit log access
- Cannot register custom scopes
- Rate limited to 100/min burst

### Pro Tier Behavior
- Up to 50 agents registered
- 50,000 requests/day across all agents
- Full scope enforcement (`write:orders`, `read:data`, etc.)
- Full audit log (last 30 days)
- Standard scope library
- Rate limited to 500/min burst

### Scale Tier Behavior
- Unlimited agents
- 500,000 requests/day across all agents
- Full scope enforcement
- Full audit log (unlimited retention)
- Custom scope registration
- Priority support
- Rate limited to 5000/min burst

## API Surface

### Authentication

All endpoints require `X-API-Key` header. Admins authenticate with their account API key to manage agents. Agents themselves authenticate with `amu_xxx.yyy` tokens.

### Account Management

#### `POST /api/v1/auth/accounts`

Create a new account.

**Request:**
```json
{
  "email": "admin@trading-bot.com",
  "name": "Trading Bot Co"
}
```

**Response (201):**
```json
{
  "account_id": "acc_abc123",
  "email": "admin@trading-bot.com",
  "name": "Trading Bot Co",
  "tier": "hobby",
  "created_at": "2026-04-14T12:00:00Z"
}
```

#### `GET /api/v1/auth/accounts/me`

Get current account details.

**Response (200):**
```json
{
  "account_id": "acc_abc123",
  "email": "admin@trading-bot.com",
  "name": "Trading Bot Co",
  "tier": "pro",
  "agents_count": 12,
  "agents_limit": 50,
  "usage_today": 1234,
  "usage_limit_today": 50000,
  "created_at": "2026-04-14T12:00:00Z"
}
```

### Agent Management

#### `POST /api/v1/auth/agents`

Register a new agent.

**Request:**
```json
{
  "name": "my-signal-agent",
  "scopes": ["read:signals", "write:orders"],
  "metadata": {
    "description": "Signals consumer for my trading bot",
    "version": "1.0.0"
  }
}
```

**Response (201):**
```json
{
  "agent_id": "agent_xyz789",
  "name": "my-signal-agent",
  "scopes": ["read:signals", "write:orders"],
  "token": "amu_my-signal-agent.eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "created_at": "2026-04-14T12:00:00Z"
}
```

Note: Token is shown only once at creation. Store securely.

#### `GET /api/v1/auth/agents`

List all agents for account.

**Response (200):**
```json
{
  "agents": [
    {
      "agent_id": "agent_xyz789",
      "name": "my-signal-agent",
      "scopes": ["read:signals", "write:orders"],
      "status": "active",
      "created_at": "2026-04-14T12:00:00Z",
      "last_seen_at": "2026-04-14T14:30:00Z",
      "requests_today": 456
    }
  ],
  "meta": {
    "total": 1,
    "limit": 50
  }
}
```

#### `GET /api/v1/auth/agents/{name}`

Get agent details.

#### `PATCH /api/v1/auth/agents/{name}`

Update agent scopes or metadata.

**Request:**
```json
{
  "scopes": ["read:signals", "write:orders", "read:portfolio"],
  "metadata": {
    "description": "Updated description"
  }
}
```

#### `DELETE /api/v1/auth/agents/{name}`

Revoke an agent. All tokens for this agent are invalidated.

**Response (204):** No content.

### Token Management

#### `POST /api/v1/auth/agents/{name}/tokens`

Generate a new token for an existing agent.

**Response (201):**
```json
{
  "token": "amu_my-signal-agent.eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "created_at": "2026-04-14T12:00:00Z"
}
```

Note: Previous tokens remain valid. Use `DELETE /api/v1/auth/tokens/{token_id}` to revoke specific tokens.

#### `GET /api/v1/auth/agents/{name}/tokens`

List all tokens for an agent (metadata only, no secrets).

**Response (200):**
```json
{
  "tokens": [
    {
      "token_id": "tok_abc123",
      "created_at": "2026-04-14T12:00:00Z",
      "last_used_at": "2026-04-14T14:30:00Z",
      "status": "active"
    }
  ]
}
```

#### `DELETE /api/v1/auth/tokens/{token_id}`

Revoke a specific token.

**Response (204):** No content.

### Token Verification

This is the core endpoint that other services call to verify agent tokens.

#### `GET /api/v1/auth/verify`

Verify an agent token and return identity.

**Headers:**
- `X-Agent-Token: amu_my-signal-agent.xxx.yyy`

**Response (200):**
```json
{
  "valid": true,
  "agent_id": "agent_xyz789",
  "name": "my-signal-agent",
  "scopes": ["read:signals", "write:orders"],
  "account_id": "acc_abc123",
  "tier": "pro"
}
```

**Response (401):** Invalid or expired token.

### Audit Log

#### `GET /api/v1/auth/audit`

Get audit log for account.

**Query parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `agent` | string | Filter by agent name |
| `event` | string | Filter by event type |
| `since` | ISO datetime | Events after this time |
| `until` | ISO datetime | Events before this time |
| `limit` | int | Max results (default 100, max 1000) |

**Response (200):**
```json
{
  "events": [
    {
      "id": "evt_abc123",
      "agent_name": "my-signal-agent",
      "event": "token.verified",
      "actor": "my-signal-agent",
      "details": {
        "ip": "203.0.113.42",
        "user_agent": "MyBot/1.0",
        "endpoint": "/api/v1/signals"
      },
      "timestamp": "2026-04-14T14:30:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "has_more": false
  }
}
```

**Note:** Pro tier: 30-day retention. Scale tier: unlimited.

### Custom Scopes (Scale tier only)

#### `POST /api/v1/auth/scopes`

Register a custom scope.

**Request:**
```json
{
  "name": "custom:prediction_market",
  "description": "Access to prediction market data"
}
```

#### `GET /api/v1/auth/scopes`

List custom scopes for account.

#### `DELETE /api/v1/auth/scopes/{scope_name}`

Delete a custom scope.

### Usage

#### `GET /api/v1/auth/usage`

Get current usage stats.

**Response (200):**
```json
{
  "period": {
    "start": "2026-04-14T00:00:00Z",
    "end": "2026-04-14T23:59:59Z"
  },
  "usage": {
    "requests": 1234,
    "limit": 50000,
    "remaining": 48766,
    "reset_at": "2026-04-14T23:59:59Z"
  },
  "agents": {
    "count": 12,
    "limit": 50
  }
}
```

### Webhooks

Receive notifications on agent events.

#### `POST /api/v1/auth/webhooks`

Register webhook URL.

**Request:**
```json
{
  "url": "https://your-server.com/webhooks/auth",
  "events": ["agent.created", "agent.revoked", "token.issued"],
  "secret": "your-webhook-secret"
}
```

## Standard Scope Library

Available scopes for Pro and Scale tiers:

| Scope | Description |
|-------|-------------|
| `read:signals` | Read signal feeds |
| `write:signals` | Publish signals |
| `read:orders` | Read order history |
| `write:orders` | Create/modify/cancel orders |
| `read:portfolio` | Read portfolio positions |
| `write:portfolio` | Modify portfolio |
| `read:market_data` | Access market data |
| `read:audit` | Access audit log |
| `admin:agents` | Manage agents |
| `admin:scopes` | Manage custom scopes (Scale only) |

## Data Model

### Extend existing `identity.agents` table

```sql
ALTER TABLE identity.agents ADD COLUMN account_id TEXT;
ALTER TABLE identity.agents ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE identity.agents ADD COLUMN webhook_url TEXT;
ALTER TABLE identity.agents ADD COLUMN webhook_secret_hash TEXT;
ALTER TABLE identity.agents ADD COLUMN custom_scopes TEXT[] DEFAULT '{}';
```

### `auth_accounts` table (new)

```sql
CREATE TABLE auth_accounts (
    account_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'hobby',
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT,
    agents_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `auth_tokens` table (new)

```sql
CREATE TABLE auth_tokens (
    token_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES identity.agents(id),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
```

### `auth_usage` table (new)

```sql
CREATE TABLE auth_usage (
    account_id TEXT NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, period_start)
);
```

## Stripe Integration

### Products

| Product | Price ID (Stripe) |
|---------|-------------------|
| Auth API Hobby | N/A |
| Auth API Pro | `price_auth_api_pro` |
| Auth API Scale | `price_auth_api_scale` |

### Flow

1. User signs up with email
2. User selects tier on pricing page
3. Redirect to Stripe Checkout
4. On success, Stripe webhook fires `checkout.session.completed`
5. Account upgraded to paid tier
6. On subscription update/cancel, adjust tier accordingly

### Webhooks to handle

- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`

## Rate Limiting

| Tier | Requests/Day | Burst |
|------|--------------|-------|
| Hobby | 1,000 | 100/min |
| Pro | 50,000 | 500/min |
| Scale | 500,000 | 5000/min |

Limits are account-wide (aggregate of all agents).

## Error Responses

| Status | Code | Description |
|--------|------|-------------|
| 400 | `invalid_request` | Malformed request |
| 401 | `invalid_api_key` | Account API key invalid |
| 401 | `invalid_token` | Agent token invalid/expired |
| 403 | `scope_required` | Missing required scope |
| 403 | `tier_limit_reached` | Agent or request limit for tier |
| 404 | `not_found` | Resource not found |
| 409 | `agent_exists` | Agent name already taken |
| 429 | `rate_limited` | Too many requests |
| 500 | `internal_error` | Server error |

## Token Format

```
amu_{agent_name}.{jwt_payload.signature}
```

Where:
- `agent_name` is lowercase, alphanumeric + underscores
- JWT payload contains: `exp`, `iat`, `nonce`
- Signature is HMAC-SHA256 of `{agent_name}.{nonce}` with server secret

Tokens expire after 90 days by default. Regenerate via API.

## Implementation Phases

### Phase 1: Account + Agent Core (4-5 days)
- `auth_accounts` table + CRUD
- Agent registration with quota enforcement
- Token generation (reuse existing SHA-256 + HMAC logic)
- Rate limiting per account

### Phase 2: Stripe Integration (2-3 days)
- Stripe checkout
- Webhook handling for subscription events
- Tier enforcement

### Phase 3: Audit + Scopes (3 days)
- Audit log table + queries
- Scope enforcement middleware
- Custom scope registration (Scale tier)

### Phase 4: Dashboard (4-5 days)
- Landing page
- Account management UI
- Agent management UI
- Usage dashboard

### Phase 5: Webhooks + Polish (2 days)
- Webhook delivery
- Email notifications
- Documentation

## Success Metrics

- Accounts by tier
- Agents per account
- Request volume per tier
- Token verification latency
- Churn rate by tier
- Custom scope adoption (Scale)
