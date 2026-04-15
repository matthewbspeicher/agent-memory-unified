# Specification: Agent Identity (Audit Phase B)

## 1. Objective

Close audit finding **#1 Identity & auth** (🟠 High) by replacing the attribution-only `verify_agent_token` foundation (shipped in `intelligence_memory` Phase 4 at `trading/api/auth.py:37-53`) with **real per-agent authentication**: pre-registered tokens, hash-based verification, scope-tagged authorization, and integration with the rate limiter from `defensive_perimeter`. After this track lands, per-agent rate limiting becomes non-bypassable, write endpoints can be gated per-scope, and audit logs meaningfully attribute actions to verified identities.

This track is **audit Phase B** — the hard gate that, once landed, enables Phase D (actually inviting external agent traffic) to proceed.

## 2. Non-goals

- **JWT token format.** The dormant JWT path at `trading/api/dependencies.py:87-114` is interesting but over-engineered for our needs. This track uses pre-shared keys stored as hashes in Postgres — simpler, stateless-enough, no JWKS infrastructure, easier to rotate. JWT remains an option for a future iteration if federation or SSO ever becomes a requirement.
- **OAuth flows.** No authorization code flow, no refresh tokens, no third-party IDP integration. Agents register once (human-in-the-loop) and hold their tokens.
- **SSO with Moltbook identity** — deferred to a dedicated federation track. This track ships our own identity layer; consuming Moltbook's identity is a separate piece.
- **Delegation or impersonation.** Every token represents exactly one agent. No "agent X acting on behalf of agent Y" semantics.
- **Expirable tokens.** For v1, tokens are long-lived until explicitly revoked. TTL-based rotation is a follow-up.
- **Automatic agent creation.** There is no self-registration from anonymous traffic. Every agent is created by an operator (or an admin-scoped caller) via a protected endpoint.
- **Retroactive rewrite of all existing route auth.** This track migrates the highest-risk routes from `verify_api_key` to `require_scope(...)`. The mechanical backfill of the remaining ~30 routes is a follow-up.

## 3. Architecture & Design

### A. Token storage — Postgres `identity` schema

Tokens are stored as hashes (never plaintext) in a new Postgres schema `identity`:

```sql
-- scripts/migrations/add-agent-identity.sql
CREATE SCHEMA IF NOT EXISTS identity;

CREATE TABLE IF NOT EXISTS identity.agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,          -- human-readable handle
    token_hash      TEXT NOT NULL,                  -- argon2id or sha256+salt
    scopes          TEXT[] NOT NULL DEFAULT '{}',   -- e.g. ['read:arena', 'participate:arena']
    tier            TEXT NOT NULL DEFAULT 'verified', -- 'anonymous' | 'verified' | 'registered' | 'admin'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,                           -- which admin created this agent
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,                    -- NULL = active; set = revoked
    revocation_reason TEXT,
    contact_email   TEXT,                           -- for abuse / ownership verification
    moltbook_handle TEXT,                           -- optional, for cross-platform identity
    notes           TEXT,                           -- operator notes
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_identity_agents_name ON identity.agents(name) WHERE revoked_at IS NULL;
CREATE INDEX idx_identity_agents_token_hash ON identity.agents(token_hash) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS identity.audit_log (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event       TEXT NOT NULL,           -- 'created' | 'revoked' | 'scope_added' | 'scope_removed' | 'token_rotated'
    agent_name  TEXT NOT NULL,
    actor       TEXT,                    -- who performed the action
    details     JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_identity_audit_ts ON identity.audit_log(ts DESC);
CREATE INDEX idx_identity_audit_agent ON identity.audit_log(agent_name, ts DESC);
```

**Hashing choice:** argon2id via `argon2-cffi` is preferred but not yet a project dependency. For v1, `hashlib.sha256` with a per-row random salt (stored alongside the hash as `salt$hash`) is acceptable and simpler. Upgrade path to argon2id is documented in §8.

### B. Token generation

Tokens are generated server-side at registration time:

```python
# trading/api/identity/tokens.py
import secrets
import hashlib

TOKEN_PREFIX = "amu_"  # agent-memory-unified

def generate_token() -> str:
    """32 bytes of entropy, URL-safe base64, prefixed for recognizability."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """sha256 + per-row random salt. Stored as 'salt$hash'."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + token).encode()).hexdigest()
    return f"{salt}${h}"

def verify_token(token: str, stored: str) -> bool:
    """Constant-time verify against a stored 'salt$hash' string."""
    if "$" not in stored:
        return False
    salt, expected = stored.split("$", 1)
    h = hashlib.sha256((salt + token).encode()).hexdigest()
    return hmac.compare_digest(h, expected)
```

**Properties:**
- Prefix `amu_` so leaked tokens in logs are recognizable + greppable
- 32 bytes = 256 bits of entropy = forever un-guessable
- Per-row salt prevents rainbow tables if the `token_hash` column ever leaks
- `compare_digest` prevents timing attacks on the comparison
- Tokens are shown **exactly once** at registration and never stored in plaintext

### C. Scope vocabulary

Scopes follow an `<action>:<resource>` pattern. Initial vocabulary:

| Scope | What it gates |
|---|---|
| `read:arena` | Arena state, leaderboard, match history (public-safe subset) |
| `participate:arena` | Enter as a gladiator, place bets, claim rewards |
| `bet:arena` | Subset of participate — only bookie market actions |
| `read:kg` | Knowledge graph queries (entity, timeline) |
| `write:kg` | Adding or invalidating KG triples (usually NOT exposed externally) |
| `read:orders` | Viewing trade history, not creating orders |
| `write:orders` | Creating, modifying, canceling orders — high trust |
| `write:predictions` | Executing prediction-market arbitrage (Kalshi/Polymarket 2-leg atomic trades, enable/disable auto-execution) — high trust |
| `read:agents` | Listing internal agents, reading their configs |
| `control:agents` | Start/stop/evolve internal agents — operator-only |
| `read:memory` | Agent memory + L0/L1 context — operator-only |
| `risk:halt` | Kill-switch trigger — operator-only (and even then, two-step confirmed) |
| `admin` | Implies all other scopes; reserved for the master `STA_API_KEY` |
| `*` | Alias for `admin` (back-compat) |

**Tier defaults:** each `tier` field value maps to a default scope set:

| Tier | Default scopes |
|---|---|
| `anonymous` | `read:arena`, `read:kg` (read subset only) |
| `verified` | `read:arena`, `participate:arena`, `bet:arena`, `read:kg` |
| `registered` | `verified` + `read:orders`, `read:agents`, `read:memory` |
| `admin` | `*` (all scopes) |

Operators can override the default on a per-agent basis (store the explicit list in `scopes`, ignore tier default). This allows fine-grained control for specific agents without needing to change the schema.

### D. FastAPI dependencies

Three new dependencies replace (or layer on top of) the existing `verify_api_key`:

```python
# trading/api/identity/dependencies.py
from fastapi import Depends, Header, HTTPException, Request
from typing import Annotated

async def resolve_identity(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    x_agent_token: Annotated[str | None, Header()] = None,
) -> "Identity":
    """Resolve the caller's identity from whichever credentials are present.

    Priority:
    1. X-Agent-Token (new, verified) — returns Identity(name=agent.name, scopes=agent.scopes)
    2. X-API-Key (legacy, master) — returns Identity(name='master', scopes=['admin'])
    3. Neither — returns Identity(name='anonymous', scopes=['read:arena', 'read:kg'])
    """
    # ... implementation in §E below


def require_scope(scope: str):
    """Dependency factory: require the caller's identity to include `scope`.

    Usage:
        @router.post("/orders", dependencies=[Depends(require_scope("write:orders"))])
        async def create_order(...): ...
    """
    async def checker(identity: Annotated["Identity", Depends(resolve_identity)]):
        if "admin" in identity.scopes or "*" in identity.scopes:
            return identity
        if scope in identity.scopes:
            return identity
        raise HTTPException(
            status_code=403,
            detail=f"scope '{scope}' required (caller has: {sorted(identity.scopes)})",
        )
    return checker


def require_any_scope(*scopes: str):
    """Dependency factory: require at least one of the listed scopes.

    Usage:
        @router.get("/agents", dependencies=[Depends(require_any_scope("read:agents", "admin"))])
        async def list_agents(...): ...
    """
    async def checker(identity: Annotated["Identity", Depends(resolve_identity)]):
        if "admin" in identity.scopes or "*" in identity.scopes:
            return identity
        if any(s in identity.scopes for s in scopes):
            return identity
        raise HTTPException(
            status_code=403,
            detail=f"one of {list(scopes)} required (caller has: {sorted(identity.scopes)})",
        )
    return checker
```

`Identity` is a small dataclass:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Identity:
    name: str
    scopes: frozenset[str]
    tier: str
    agent_id: str | None = None  # UUID from identity.agents; None for anonymous/master
```

### E. Integration with existing `verify_agent_token`

The Phase 4 `verify_agent_token` at `trading/api/auth.py:37-53` is **attribution-only** and **bypassable** — any string in `X-Agent-Token` becomes the identity. This track does NOT delete that function (keeps back-compat for the 3 KG read endpoints that currently use it). Instead:

- `verify_agent_token` — **unchanged**, still attribution-only, still used by the 3 KG read endpoints for `queried_by` logging. Future cleanup: migrate those endpoints to `Depends(resolve_identity)` and delete the old function.
- `resolve_identity` — **new**, the verified version. Looks up the `X-Agent-Token` value against `identity.agents.token_hash`. Unknown tokens get 401. Known-but-revoked tokens get 403 with a clear error.
- `require_scope`, `require_any_scope` — **new**, scope enforcement built on `resolve_identity`.
- `verify_api_key` — **unchanged**, still works, but becomes equivalent to `require_scope("admin")` when layered. High-risk routes migrate to `require_scope(...)` explicitly; lower-risk routes keep `verify_api_key` for back-compat during the transition.

### F. Registration endpoints (admin-only)

```python
# trading/api/routes/identity.py
router = APIRouter(prefix="/api/v1/identity", tags=["identity"])

@router.post("/agents", dependencies=[Depends(require_scope("admin"))])
async def register_agent(
    request: AgentRegistrationRequest,
    admin: Annotated[Identity, Depends(resolve_identity)],
) -> AgentRegistrationResponse:
    """Create a new agent identity. Admin-only.

    Returns the plaintext token exactly once. The operator is responsible
    for delivering it to the agent's owner securely (out of band).
    """
    token = generate_token()
    token_hash = hash_token(token)
    agent = await IdentityStore.create(
        name=request.name,
        token_hash=token_hash,
        scopes=request.scopes or tier_default_scopes(request.tier),
        tier=request.tier,
        contact_email=request.contact_email,
        moltbook_handle=request.moltbook_handle,
        created_by=admin.name,
    )
    # Audit log
    await IdentityStore.audit(
        event="created",
        agent_name=request.name,
        actor=admin.name,
        details={"tier": request.tier, "scopes": request.scopes},
    )
    return AgentRegistrationResponse(
        name=agent.name,
        id=agent.id,
        tier=agent.tier,
        scopes=agent.scopes,
        token=token,  # shown once; not stored
        warning="Save this token now. It will not be shown again. Hash is stored, token is not.",
    )


@router.get("/me")
async def me(identity: Annotated[Identity, Depends(resolve_identity)]) -> AgentProfile:
    """Return the caller's own profile. No token. Safe for anonymous callers."""
    return AgentProfile(
        name=identity.name,
        scopes=sorted(identity.scopes),
        tier=identity.tier,
    )


@router.post("/agents/{name}/revoke", dependencies=[Depends(require_scope("admin"))])
async def revoke_agent(
    name: str,
    request: RevocationRequest,
    admin: Annotated[Identity, Depends(resolve_identity)],
) -> dict:
    """Revoke an agent's token. Admin-only. Irreversible without re-registration."""
    await IdentityStore.revoke(name=name, reason=request.reason, actor=admin.name)
    await IdentityStore.audit(
        event="revoked",
        agent_name=name,
        actor=admin.name,
        details={"reason": request.reason},
    )
    return {"revoked": name, "ts": datetime.utcnow().isoformat()}


@router.post("/agents/{name}/rotate", dependencies=[Depends(require_scope("admin"))])
async def rotate_agent_token(
    name: str,
    admin: Annotated[Identity, Depends(resolve_identity)],
) -> AgentRegistrationResponse:
    """Generate a new token for an existing agent. Old token stops working immediately."""
    new_token = generate_token()
    new_hash = hash_token(new_token)
    await IdentityStore.update_token_hash(name=name, token_hash=new_hash)
    await IdentityStore.audit(
        event="token_rotated",
        agent_name=name,
        actor=admin.name,
        details={},
    )
    return AgentRegistrationResponse(
        name=name,
        id=(await IdentityStore.get_by_name(name)).id,
        tier=(await IdentityStore.get_by_name(name)).tier,
        scopes=(await IdentityStore.get_by_name(name)).scopes,
        token=new_token,
        warning="Old token invalidated. Deliver new token securely; it will not be shown again.",
    )
```

### G. Route migration — which routes become scope-gated in Phase B

The mechanical backfill of all write routes is **out of scope** (same follow-up pattern as `defensive_perimeter`'s audit decorator). Phase B migrates the highest-value routes:

| Route | Current auth | New auth |
|---|---|---|
| `POST /api/v1/orders` | `verify_api_key` | `require_scope("write:orders")` |
| `POST /api/v1/trades` | `verify_api_key` | `require_scope("write:orders")` |
| `POST /api/v1/risk/kill-switch` | `verify_api_key` | `require_scope("risk:halt")` + two-step confirm from defensive_perimeter |
| `POST /api/v1/agents/{name}/start` | `verify_api_key` | `require_scope("control:agents")` |
| `POST /api/v1/agents/{name}/stop` | `verify_api_key` | `require_scope("control:agents")` |
| `POST /api/v1/agents/{name}/scan` | `verify_api_key` | `require_scope("control:agents")` |
| `POST /api/v1/agents/{name}/evolve` | `verify_api_key` | `require_scope("control:agents")` |
| `POST /api/v1/competition/matches/{id}/bet` | `verify_api_key` | `require_scope("bet:arena")` |
| `POST /api/v1/competition/matches/{id}/settle` | `verify_api_key` | `require_scope("admin")` (match settlement is operator-only) |
| `POST /api/v1/identity/agents` | NEW | `require_scope("admin")` |
| `POST /api/v1/identity/agents/{name}/revoke` | NEW | `require_scope("admin")` |

The existing master `STA_API_KEY` continues to work on all these routes because of the `admin` scope back-compat in `require_scope`. No existing operator workflows break.

Everything else keeps `verify_api_key` for back-compat. The remaining ~30 routes can migrate route-by-route in follow-up PRs without blocking this track.

### H. Rate limiter integration with `defensive_perimeter`

After Phase B lands, the rate limiter's bucket key changes from "the raw `X-Agent-Token` value" (bypassable) to "the **verified** agent name from `resolve_identity`" (non-bypassable). The change is a one-line update in the rate limiter's key function:

```python
# trading/api/middleware/limiter.py — after Phase B
async def bucket_key(request: Request) -> str:
    identity = await resolve_identity_unchecked(request)  # returns anonymous on failure
    if identity.name == "anonymous":
        return f"anon:{request.client.host}"  # IP-based for anonymous
    return f"agent:{identity.name}"  # verified agent name
```

**`resolve_identity_unchecked`** is a middleware-safe version that doesn't raise on auth failure (it returns anonymous Identity). The normal `resolve_identity` dependency is the one that raises 401 on unknown tokens.

**Net effect:** after Phase B, a malicious caller rotating `X-Agent-Token` values still gets rate-limited because unknown tokens fail verification and fall back to the anonymous (IP-based) bucket. Only known-and-valid tokens get a per-agent bucket, and those buckets are non-bypassable because the token itself is pre-registered.

This closes the "per-agent rate limiting is bypassable" caveat from `defensive_perimeter`'s spec §A.

### I. Backwards compatibility

- `STA_API_KEY` master key continues to work everywhere. It's treated as implicit `admin` scope.
- `verify_api_key` as a dependency continues to work. It's now equivalent to `require_scope("admin")` but keeps its old name for back-compat.
- The Phase 4 `verify_agent_token` function at `trading/api/auth.py:37-53` is **not deleted**. The 3 KG read endpoints that use it continue to work (they'll get attribution-only identity in the `queried_by` field). Future cleanup moves them to `Depends(resolve_identity)` and deletes the old function; tracked as follow-up.
- The frontend uses `STA_API_KEY` via `VITE_TRADING_API_KEY` per CLAUDE.md — unchanged, still works.
- No existing route returns 401 or 403 after this track lands unless it's explicitly migrated to `require_scope(...)`.

## 4. Tech Stack

- **Language:** Python 3.13 (matches existing trading engine)
- **Database:** Postgres 16 (same instance as the trading engine, new `identity` schema)
- **Hashing:** `hashlib.sha256` + random salt for v1; argon2id upgrade path in §8
- **Token generation:** `secrets.token_urlsafe` (stdlib)
- **Timing-safe comparison:** `hmac.compare_digest` (stdlib)
- **FastAPI dependencies:** standard `Depends` pattern
- **Testing:** `pytest` + `TestClient`

No new dependencies. All stdlib or already-present.

## 5. Dependencies

### Hard dependencies

- **`defensive_perimeter` Phase A landed** — the rate limiter must exist so this track can update its bucket key function. Phase A's `02541e2` commit (pending verification) satisfies this.
- **Postgres connection pool** — this track uses the same `STA_DATABASE_URL` as the trading engine. The `identity` schema migration lands in `scripts/migrations/`.

### Soft dependencies

- **`intelligence_memory` Phase 4** — the attribution-only `verify_agent_token` foundation exists and stays in place. This track doesn't replace it; it adds a real version alongside.
- **`public_surface` track** — public endpoints will eventually migrate from anonymous-only to optionally-authenticated (a verified agent hitting `/engine/v1/public/*` should get a higher rate limit tier). Not blocking; public_surface can ship with anonymous-only and get identity-awareness as a follow-up.

### Unblocks

- **`moltbook_publisher` track** — the publisher authenticates to Moltbook as us (outbound), but the `register-wizard` subcommand and the one-time registration step are independent of our own identity layer. That said, once Phase B lands, the publisher's own operator-facing CLI could use `require_scope("admin")` for its own protection.
- **Moltbook publication gate** — audit Phase B is the single biggest outstanding gate. After this lands, the only remaining gates are: `public_surface` implementation, `moltbook_publisher` implementation, 2-3 polished posts, and the human Moltbook registration step.

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Registration endpoint leak lets attackers self-register | Registration requires `admin` scope. Master `STA_API_KEY` is the only initial admin identity. Attackers would need the master key first, at which point registration is the smallest of our problems. |
| Token hash column leaks from a DB dump | Per-row salts prevent rainbow tables. Leaked hashes can't be reversed without the salts AND the tokens are 256 bits of entropy. |
| Token shown once and lost | Re-register with a new name OR use the rotate endpoint to generate a new token for the same agent. Rotate is admin-only to prevent denial-of-service via token churn. |
| Revoked tokens continue to work briefly due to caching | Cache TTL kept short (≤60s) for identity lookups. A token revocation incident has a max 60-second exposure window. |
| Scope inflation — operators add `admin` to too many agents | Spec mandates that `admin` is reserved for the master key. Non-master agents max out at `registered` tier's default scope set. Documented in the runbook. |
| Back-compat migration breaks existing internal tooling | All existing routes keep working because `verify_api_key` is unchanged and the master key has admin scope. Only NEW routes or explicitly-migrated routes use `require_scope`. |
| Identity schema migration conflicts with the `kg` schema from intelligence_memory | Both use `scripts/migrations/` directory. Migrations are applied in alphabetical order; the new file is named `add-agent-identity.sql` which sorts after the existing migrations. |
| Argon2id upgrade path is messy | Stored format is `salt$hash`. A future upgrade adds a `hash_algo` column with default `sha256`, and on next successful verify, the stored hash is rewritten with argon2id. Lazy migration, no downtime. |
| Rate limiter bucket key change causes legitimate callers to suddenly be rate-limited differently | The change from "raw X-Agent-Token" to "verified agent name" is the same string in 99% of cases (because honest callers use consistent names). Only bypassers see a change. Deploy with the existing `STA_RATE_LIMIT_ENABLED` flag from Phase A for emergency rollback. |
| Admin agent accidentally revokes the master key | `STA_API_KEY` is NOT stored in `identity.agents`. It's a config value read from the env. There is no `revoke` operation against it. The only way to "revoke" the master key is to rotate `STA_API_KEY` in the env. |

## 7. Quality Gates

- [ ] **Migration applies cleanly** — `scripts/migrations/add-agent-identity.sql` creates the `identity` schema without conflict with `kg` or public tables.
- [ ] **Registration flow works end-to-end** — unit test registers a new agent via the admin endpoint, verifies the token is returned exactly once, hits `/api/v1/identity/me` with the token, confirms identity resolution.
- [ ] **Revocation takes effect within 60s** — unit test creates an agent, revokes it, waits for cache expiry, asserts 403 on subsequent calls.
- [ ] **Scope enforcement on highest-risk routes** — integration test hits each migrated route with a token that lacks the required scope, asserts 403. Hits the same route with a token that has the scope, asserts success.
- [ ] **Back-compat master key** — integration test uses `X-API-Key: $STA_API_KEY` against every migrated route, asserts success (master key has implicit admin scope).
- [ ] **Unknown token returns 401** — hitting any `require_scope`-gated route with `X-Agent-Token: amu_notreal` returns 401 (not 403; unknown ≠ forbidden).
- [ ] **Anonymous caller gets the anonymous tier** — no auth headers → `resolve_identity` returns `name='anonymous'` with `scopes=['read:arena', 'read:kg']`. Hitting a `require_scope("write:orders")` route without auth returns 403.
- [ ] **Rate limiter bucket key uses verified name** — an unknown `X-Agent-Token` gets IP-bucketed (not token-bucketed); a verified token gets agent-bucketed.
- [ ] **No secrets leak in error messages** — 401/403 responses don't echo back the submitted token, just the scope name.
- [ ] **Audit log captures all identity events** — `created`, `revoked`, `token_rotated` events land in `identity.audit_log` with the admin actor name.
- [ ] **Integration with defensive_perimeter's `@audit_event`** — migrated routes emit audit events with the verified `agent_id` (not just "anonymous" or "master").

## 8. Out of scope / future work

- **Argon2id upgrade** — add `hash_algo` column, lazy-rewrite on verify. Follow-up PR.
- **JWT token format** — if federation or SSO becomes a requirement, evaluate moving from pre-shared keys to JWT. Dormant JWT path in `dependencies.py:87-114` is the starting point.
- **Token TTL / expiration** — auto-expire tokens after a configurable duration, require rotate. Follow-up.
- **Scope inheritance / hierarchies** — e.g., `admin` implies all other scopes (already true), `registered` implies `verified` (not yet implemented — each scope is currently flat).
- **Per-agent rate limit tier overrides** — e.g., "this specific agent gets 500 req/min instead of the default 300 for their tier." Schema supports it via `metadata`, enforcement is a follow-up.
- **Moltbook identity federation** — accepting Moltbook-signed tokens as a valid identity source. Separate track.
- **UI for agent management** — a frontend page for operators to create, view, and revoke agents. For v1, CLI-only via curl to the admin endpoints.
- **Backfill of the remaining ~30 write routes** — mechanical migration, follow-up PR.
- **Delegation / impersonation** — "agent X acting on behalf of user Y." Not in scope.
- **Rate limiting on the identity endpoints themselves** — admin endpoints inherit the master tier's 300 req/min, which is fine for v1. A dedicated tighter limit on registration to prevent accidental DoS is a follow-up.

## 9. References

- Audit: `docs/superpowers/specs/2026-04-10-agent-readiness-audit.md`
- Audit cross-ref: `conductor/tracks/agent_identity/audit-cross-ref.md`
- Sibling tracks: `defensive_perimeter` (hard dependency — consumes rate limiter), `intelligence_memory` (Phase 4 attribution-only foundation stays in place), `public_surface` (will benefit from identity-awareness as a follow-up)
- Dormant JWT path: `trading/api/dependencies.py:87-114`
- Current attribution-only function: `trading/api/auth.py:37-53`
- Memory: `reference_agent_readiness_audit.md` (audit finding #1 closure status), `feedback_parallel_opencode_stream.md` (coordination with Gemini's parallel work)
