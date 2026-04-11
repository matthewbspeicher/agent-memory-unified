# Specification: Defensive Perimeter (Audit Phase A)

## 1. Objective
Establish a robust defensive layer for the trading API to mitigate risks from external agent influx (Moltbook) and internal misconfigurations. This track focuses on rate limiting, comprehensive audit logging, and an protected global kill-switch.

## 2. Architecture & Design

### A. Tiered Rate Limiting (slowapi + Redis)
- **Engine:** Use `slowapi` (FastAPI-native) with `RedisBackend` for distributed state.
- **Identity Resolver:** Use `X-Agent-Token` (with `verify_agent_token` attribution) or `X-API-Key` hash.
- **Tiers:**
    - **Anonymous (No Auth):** 10 req/min. Restricted to a read-only allowlist (`/status`, `/metrics`, `/kg/stats`).
    - **Verified Agent:** 60 req/min. Enforced via `X-Agent-Token`.
    - **Master (X-API-Key):** 300 req/min.
- **Storage Key Pattern:** `rate_limit:{identity}:{minute|hour}` in Redis.

### B. Structured Auditing (@audit_event)
- **Decorator:** `@audit_event(action_name)` implemented in `trading/utils/audit.py`.
- **Targeting:**
    - **HTTP Layer:** Apply to high-risk route handlers in `api/routes/`.
    - **Business Layer:** Apply to critical methods like `Broker.execute_order` and `AgentRunner.stop_agent`.
- **Failure Semantics:** Audit logging MUST be "best-effort" for the business logic. If the audit write fails, the action should still proceed, but a critical error must be logged to the standard application log.
- **Data Sink:**
    - `log_event()` for real-time observability.
    - `audit_logs` table in PostgreSQL for forensic persistence.

### C. Global Kill-Switch Redesign
- **State Storage:** Redis key `kill_switch:active` (Boolean).
- **Confirmation Flow:** Two-step pattern for `POST /api/v1/risk/kill-switch`.
    1. `/initiate` -> Returns a 60s single-use `confirmation_token`.
    2. `/confirm?token=XYZ` -> Sets `kill_switch:active` to `true`.
- **In-flight Semantics:** When active, the kill-switch halts NEW scans and NEW orders. In-flight asyncio tasks are allowed to complete their current iteration but must exit at the next check-point.
- **Gate:** All `POST/PUT/DELETE` routes must check the kill-switch via a FastAPI dependency.

## 3. Database Schema (Postgres)

```sql
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    action_name TEXT NOT NULL,
    actor_id TEXT NOT NULL,      -- agent_id or 'anonymous'
    actor_type TEXT NOT NULL,    -- 'agent', 'master', 'system'
    resource_id TEXT,            -- ticker, hotkey, or agent_name
    status TEXT NOT NULL,        -- 'initiated', 'success', 'failed'
    duration_ms INTEGER,
    request_id TEXT,             -- Correlation with OTEL traces
    payload JSONB,               -- Request/params
    error_detail TEXT,           -- Stack trace or error message
    client_ip TEXT
);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id);
```

## 4. Tech Stack
- **Library:** `slowapi` for rate limiting.
- **Database:** PostgreSQL 16 (for `audit_logs`).
- **Distributed State:** Redis (for rate limits and kill-switch flag).

## 5. Risks & Mitigations
- **Redis Latency:** Rate limiting adds ~5-10ms per request. Mitigated by using a local Redis instance and `aioredis` connection pooling.
- **Log Sprawl:** `audit_logs` can grow rapidly. Mitigated by a 30-day retention policy (Task for Phase E).
- **Accidental Lockout:** Kill-switch `confirmation_token` expires in 60s to prevent stale activation tokens from being misused.
