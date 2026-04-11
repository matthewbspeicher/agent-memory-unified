# Implementation Plan: Defensive Perimeter (Audit Phase A)

This plan implements the defensive infrastructure required to protect the trading API from unauthorized access and excessive load.

## Phase A: Baseline Defense [x]

### Task 1: Rate Limiting Infrastructure [x]
- [x] Install `slowapi` and `aioredis` (if not present) in `trading/requirements.txt`.
- [x] Implement `RedisRateLimiter` in `trading/api/middleware/limiter.py`.
- [x] Configure the three tiers (Anon, Verified, Master) in `trading/config.py`.
- [x] Apply global rate limiting to `app.py`.

### Task 2: Structured Audit Logging [x]
- [x] Create `trading/utils/audit.py` with the `@audit_event` decorator.
- [x] Implement the `AuditLog` Postgres model and migration.
- [x] Instrument the first 5 high-risk routes:
    - `POST /api/v1/risk/kill-switch`
    - `POST /api/v1/orders`
    - `POST /api/v1/trades`
    - `POST /api/v1/agents/{name}/scan`
    - `POST /api/v1/competition/settle`

### Task 3: Protected Kill-Switch [x]
- [x] Implement Redis-backed kill-switch state in `trading/storage/risk.py`.
- [x] Create the `/kill-switch/initiate` and `/kill-switch/confirm` endpoints in `trading/api/routes/risk.py`.
- [x] Implement the `KillSwitchActive` FastAPI dependency to block mutations.
- [x] Wire the kill-switch check into `AgentRunner._execute_scan`.

---

## Quality Gates
- [ ] **Rate Limit Test:** Verify anonymous requests are throttled after 10 req/min.
- [ ] **Audit Trail Test:** Verify a `POST /orders` call creates a corresponding entry in the `audit_logs` table.
- [ ] **Kill-Switch Test:** Verify all `POST` requests return 503 Service Unavailable when `kill_switch:active` is true in Redis.
- [ ] **Confirmation Test:** Verify the kill-switch cannot be activated without a valid, unexpired confirmation token.
