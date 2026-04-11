# Implementation Plan: Defensive Perimeter (Audit Phase A)

This plan implements the defensive infrastructure required to protect the trading API from unauthorized access and excessive load.

## Phase A: Baseline Defense [ ]

### Task 1: Rate Limiting Infrastructure [ ]
- [ ] Install `slowapi` and `aioredis` (if not present) in `trading/requirements.txt`.
- [ ] Implement `RedisRateLimiter` in `trading/api/middleware/limiter.py`.
- [ ] Configure the three tiers (Anon, Verified, Master) in `trading/config.py`.
- [ ] Apply global rate limiting to `app.py`.

### Task 2: Structured Audit Logging [ ]
- [ ] Create `trading/utils/audit.py` with the `@audit_event` decorator.
- [ ] Implement the `AuditLog` Postgres model and migration.
- [ ] Instrument the first 5 high-risk routes:
    - `POST /api/v1/risk/kill-switch`
    - `POST /api/v1/orders`
    - `POST /api/v1/trades`
    - `POST /api/v1/agents/{name}/scan`
    - `POST /api/v1/competition/settle`

### Task 3: Protected Kill-Switch [ ]
- [ ] Implement Redis-backed kill-switch state in `trading/storage/risk.py`.
- [ ] Create the `/kill-switch/initiate` and `/kill-switch/confirm` endpoints in `trading/api/routes/risk.py`.
- [ ] Implement the `KillSwitchActive` FastAPI dependency to block mutations.
- [ ] Wire the kill-switch check into `AgentRunner._execute_scan`.

---

## Quality Gates
- [ ] **Rate Limit Test:** Verify anonymous requests are throttled after 10 req/min.
- [ ] **Audit Trail Test:** Verify a `POST /orders` call creates a corresponding entry in the `audit_logs` table.
- [ ] **Kill-Switch Test:** Verify all `POST` requests return 503 Service Unavailable when `kill_switch:active` is true in Redis.
- [ ] **Confirmation Test:** Verify the kill-switch cannot be activated without a valid, unexpired confirmation token.
