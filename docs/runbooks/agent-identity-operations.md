# Agent Identity Operations Runbook

## Overview

The Agent Identity system provides per-agent authentication with hash-based token verification, scope-tagged authorization, and rate limiter integration.

## Key Concepts

- **Agent**: A pre-registered entity with a unique name and API token
- **Token**: SHA-256 hashed and stored in `agents` table
- **Scopes**: Granular permissions (e.g., `write:orders`, `risk:halt`, `control:agents`)
- **Tiers**: Anonymous, public, premium, admin

## Registering a New Agent

### Via API (requires admin scope or master API key)

```bash
curl -X POST http://localhost:8080/api/v1/agents \
  -H "X-API-Key: $STA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-trading-bot",
    "scopes": ["write:orders", "read:portfolio"],
    "tier": "public",
    "notes": "Automated trading bot for equities"
  }'
```

Response includes the **plain-text token** (only shown once):

```json
{
  "name": "my-trading-bot",
  "token": "snty_abc123...",
  "scopes": ["write:orders", "read:portfolio"],
  "tier": "public"
}
```

**Save this token securely** — it cannot be retrieved later.

### Using the Token

Include the token in requests via the `X-Agent-Token` header:

```bash
curl http://localhost:8080/api/v1/portfolio \
  -H "X-Agent-Token: snty_abc123..."
```

## Revoking an Agent

Revoke immediately (takes effect within 60s due to cache TTL):

```bash
curl -X DELETE http://localhost:8080/api/v1/agents/my-trading-bot \
  -H "X-API-Key: $STA_API_KEY"
```

## Token Rotation

1. Register a new agent with the same name and scopes
2. Update all clients to use the new token
3. Delete the old agent

## Master Key Leak Response

1. **Rotate `STA_API_KEY`** in `.env` and restart the trading engine
2. Revoke all agent tokens as a precaution
3. Re-register agents with new tokens
4. Audit `audit_logs` table for suspicious activity

## Common Scope Patterns

| Use Case | Scopes Required |
|----------|-----------------|
| Read-only monitoring | `read:portfolio`, `read:arena` |
| Order execution | `write:orders`, `read:portfolio` |
| Risk management | `risk:halt`, `read:portfolio` |
| Agent orchestration | `control:agents`, `read:arena` |
| Full access | `admin` |

## Rate Limiting

| Tier | Rate Limit | Bucket Key |
|------|------------|------------|
| Verified Agent | 60/minute | `tier:agent:{agent_name}` |
| Master | 300/minute | `tier:master:{key_hash}` |
| Anonymous | 10/minute | `tier:anon:{ip}` |

Unknown/invalid tokens fall back to anonymous tier (IP-based bucketing).

## Troubleshooting

### 403 Forbidden

- Check agent has required scope for the endpoint
- Verify token is not revoked
- Confirm token is being sent in `X-Agent-Token` header

### 429 Too Many Requests

- Wait for rate limit window to reset
- Upgrade to higher tier if applicable
- Use verified token instead of anonymous

### 500 Internal Server Error

- Check `identity_store` is initialized
- Verify PostgreSQL connection
- Check audit logs for detailed error
