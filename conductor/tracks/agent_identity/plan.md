# Implementation Plan: Agent Identity (Audit Phase B)

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. TDD where practical.

**Goal:** Close audit finding #1 by shipping real per-agent authentication: pre-registered tokens, hash-based verification, scope-tagged authorization, integration with the rate limiter from `defensive_perimeter`.

**Spec:** `conductor/tracks/agent_identity/spec.md`

**Hard dependency:** `defensive_perimeter` Phase A landed (`02541e2`, pending verification). If verification reveals the Phase A implementation diverges from its v2 spec, this track's Task 7 (rate limiter bucket key update) needs to adapt.

---

## Phase 1: Schema and storage

### Task 1: Create the `identity` schema migration

**Files:**
- Create: `scripts/migrations/add-agent-identity.sql`
- Modify: `scripts/init-trading-tables.sql` (add `\i migrations/add-agent-identity.sql` include if that's the pattern)
- Create: `trading/tests/integration/test_identity_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/integration/test_identity_schema.py
import pytest
import asyncpg

@pytest.mark.integration
@pytest.mark.asyncio
async def test_identity_schema_exists(postgres_dsn):
    conn = await asyncpg.connect(postgres_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'identity')"
        )
        assert exists, "identity schema not created"

        agents_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'identity' AND table_name = 'agents')"
        )
        assert agents_exists

        audit_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'identity' AND table_name = 'audit_log')"
        )
        assert audit_exists
    finally:
        await conn.close()
```

- [ ] **Step 2: Run test, verify failure** (schema doesn't exist).

- [ ] **Step 3: Write the migration file** from spec §3.A verbatim:

```sql
-- scripts/migrations/add-agent-identity.sql
CREATE SCHEMA IF NOT EXISTS identity;

CREATE TABLE IF NOT EXISTS identity.agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    token_hash      TEXT NOT NULL,
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    tier            TEXT NOT NULL DEFAULT 'verified',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revocation_reason TEXT,
    contact_email   TEXT,
    moltbook_handle TEXT,
    notes           TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_identity_agents_name ON identity.agents(name) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_identity_agents_token_hash ON identity.agents(token_hash) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS identity.audit_log (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event       TEXT NOT NULL,
    agent_name  TEXT NOT NULL,
    actor       TEXT,
    details     JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_identity_audit_ts ON identity.audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_identity_audit_agent ON identity.audit_log(agent_name, ts DESC);
```

- [ ] **Step 4: Apply to local Postgres**

```bash
docker exec -i agent-memory-unified-postgres-1 psql -U postgres -d agent_memory < scripts/migrations/add-agent-identity.sql
```

Expected: no errors; schema and tables created.

- [ ] **Step 5: Run the integration test**

```bash
cd trading && python -m pytest tests/integration/test_identity_schema.py -v -m integration
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/migrations/add-agent-identity.sql trading/tests/integration/test_identity_schema.py
git commit -m "feat(identity): add Postgres identity schema for agent auth"
```

---

## Phase 2: Token generation and hashing

### Task 2: Token primitives (`trading/api/identity/tokens.py`)

**Files:**
- Create: `trading/api/identity/__init__.py` (empty)
- Create: `trading/api/identity/tokens.py`
- Create: `trading/tests/unit/test_identity_tokens.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/unit/test_identity_tokens.py
import pytest
from api.identity.tokens import generate_token, hash_token, verify_token, TOKEN_PREFIX


def test_generate_token_has_prefix_and_sufficient_entropy():
    t = generate_token()
    assert t.startswith(TOKEN_PREFIX)
    # Prefix + 32 URL-safe base64 bytes → at least 40 chars total
    assert len(t) >= 40
    # Two generations should not collide
    assert generate_token() != generate_token()


def test_hash_token_produces_salted_output():
    h = hash_token("amu_test_token")
    assert "$" in h
    salt, digest = h.split("$", 1)
    assert len(salt) == 32  # 16 bytes hex
    assert len(digest) == 64  # sha256 hex


def test_verify_token_correct_returns_true():
    token = generate_token()
    stored = hash_token(token)
    assert verify_token(token, stored) is True


def test_verify_token_wrong_returns_false():
    token = generate_token()
    stored = hash_token(token)
    assert verify_token(token + "x", stored) is False
    assert verify_token("completely_different", stored) is False


def test_verify_token_malformed_stored_returns_false():
    assert verify_token("whatever", "no_dollar_sign") is False
    assert verify_token("whatever", "") is False
```

- [ ] **Step 2: Run tests, verify failures** (module not found).

- [ ] **Step 3: Implement** `trading/api/identity/tokens.py` per spec §3.B verbatim.

- [ ] **Step 4: Run tests, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add trading/api/identity/__init__.py trading/api/identity/tokens.py trading/tests/unit/test_identity_tokens.py
git commit -m "feat(identity): add token generation, hashing, and verification primitives"
```

---

## Phase 3: Identity store

### Task 3: `IdentityStore` with CRUD + audit logging

**Files:**
- Create: `trading/api/identity/store.py`
- Create: `trading/tests/integration/test_identity_store.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/integration/test_identity_store.py
import pytest
from api.identity.store import IdentityStore
from api.identity.tokens import hash_token


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_lookup_by_name(identity_store: IdentityStore):
    token_hash = hash_token("amu_test1")
    agent = await identity_store.create(
        name="test-agent-1",
        token_hash=token_hash,
        scopes=["read:arena"],
        tier="verified",
        created_by="test",
    )
    assert agent.name == "test-agent-1"
    assert "read:arena" in agent.scopes

    fetched = await identity_store.get_by_name("test-agent-1")
    assert fetched is not None
    assert fetched.name == "test-agent-1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lookup_by_token_hash_returns_agent(identity_store: IdentityStore):
    token = "amu_test_lookup"
    h = hash_token(token)
    await identity_store.create(name="lookup-agent", token_hash=h, scopes=[], tier="verified", created_by="t")
    fetched = await identity_store.get_by_token_hash(h)
    assert fetched is not None
    assert fetched.name == "lookup-agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoked_agent_not_returned_by_lookups(identity_store: IdentityStore):
    h = hash_token("amu_to_revoke")
    await identity_store.create(name="revoke-me", token_hash=h, scopes=[], tier="verified", created_by="t")
    await identity_store.revoke(name="revoke-me", reason="test", actor="t")
    assert await identity_store.get_by_name("revoke-me") is None
    assert await identity_store.get_by_token_hash(h) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_log_records_creation_and_revocation(identity_store: IdentityStore):
    h = hash_token("amu_audit")
    await identity_store.create(name="audit-agent", token_hash=h, scopes=[], tier="verified", created_by="t")
    await identity_store.audit(event="created", agent_name="audit-agent", actor="t", details={})
    await identity_store.revoke(name="audit-agent", reason="test", actor="t")
    await identity_store.audit(event="revoked", agent_name="audit-agent", actor="t", details={"reason": "test"})

    events = await identity_store.get_audit_log(agent_name="audit-agent")
    assert len(events) >= 2
    event_types = {e["event"] for e in events}
    assert "created" in event_types
    assert "revoked" in event_types
```

- [ ] **Step 2: Run tests, verify failures.**

- [ ] **Step 3: Implement** `trading/api/identity/store.py`

```python
# trading/api/identity/store.py
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import asyncpg


@dataclass(frozen=True)
class AgentRecord:
    id: str
    name: str
    token_hash: str
    scopes: list[str]
    tier: str
    created_at: datetime
    revoked_at: datetime | None
    contact_email: str | None
    moltbook_handle: str | None
    metadata: dict


class IdentityStore:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create(
        self,
        *,
        name: str,
        token_hash: str,
        scopes: list[str],
        tier: str,
        created_by: str | None = None,
        contact_email: str | None = None,
        moltbook_handle: str | None = None,
    ) -> AgentRecord:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO identity.agents
                    (name, token_hash, scopes, tier, created_by, contact_email, moltbook_handle)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, name, token_hash, scopes, tier, created_at, revoked_at,
                          contact_email, moltbook_handle, metadata
                """,
                name, token_hash, scopes, tier, created_by, contact_email, moltbook_handle,
            )
        return self._row_to_record(row)

    async def get_by_name(self, name: str) -> AgentRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, token_hash, scopes, tier, created_at, revoked_at,
                       contact_email, moltbook_handle, metadata
                FROM identity.agents
                WHERE name = $1 AND revoked_at IS NULL
                """,
                name,
            )
        return self._row_to_record(row) if row else None

    async def get_by_token_hash(self, token_hash: str) -> AgentRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, token_hash, scopes, tier, created_at, revoked_at,
                       contact_email, moltbook_handle, metadata
                FROM identity.agents
                WHERE token_hash = $1 AND revoked_at IS NULL
                """,
                token_hash,
            )
        return self._row_to_record(row) if row else None

    async def revoke(self, *, name: str, reason: str, actor: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE identity.agents
                SET revoked_at = NOW(), revocation_reason = $2
                WHERE name = $1 AND revoked_at IS NULL
                """,
                name, reason,
            )

    async def update_token_hash(self, *, name: str, token_hash: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE identity.agents SET token_hash = $2 WHERE name = $1 AND revoked_at IS NULL",
                name, token_hash,
            )

    async def audit(
        self,
        *,
        event: str,
        agent_name: str,
        actor: str | None,
        details: dict,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO identity.audit_log (event, agent_name, actor, details)
                VALUES ($1, $2, $3, $4)
                """,
                event, agent_name, actor, json.dumps(details),
            )

    async def get_audit_log(self, *, agent_name: str, limit: int = 100) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ts, event, agent_name, actor, details
                FROM identity.audit_log
                WHERE agent_name = $1
                ORDER BY ts DESC
                LIMIT $2
                """,
                agent_name, limit,
            )
        return [
            {
                "ts": r["ts"].isoformat(),
                "event": r["event"],
                "agent_name": r["agent_name"],
                "actor": r["actor"],
                "details": json.loads(r["details"]) if isinstance(r["details"], str) else r["details"],
            }
            for r in rows
        ]

    def _row_to_record(self, row) -> AgentRecord:
        return AgentRecord(
            id=str(row["id"]),
            name=row["name"],
            token_hash=row["token_hash"],
            scopes=list(row["scopes"]),
            tier=row["tier"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            contact_email=row["contact_email"],
            moltbook_handle=row["moltbook_handle"],
            metadata=row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"]),
        )
```

- [ ] **Step 4: Add fixture for `identity_store` in `conftest.py`** — provisions a test Postgres pool, yields an `IdentityStore`, tears down by truncating `identity.agents` and `identity.audit_log`.

- [ ] **Step 5: Run tests, verify pass.**

- [ ] **Step 6: Commit**

```bash
git add trading/api/identity/store.py trading/tests/integration/test_identity_store.py trading/tests/conftest.py
git commit -m "feat(identity): add IdentityStore with CRUD + audit logging against identity schema"
```

---

## Phase 4: FastAPI dependencies

### Task 4: `resolve_identity`, `require_scope`, `require_any_scope`

**Files:**
- Create: `trading/api/identity/dependencies.py`
- Create: `trading/tests/unit/test_identity_dependencies.py`
- Modify: `trading/api/app.py` (provide `IdentityStore` via app.state)

- [ ] **Step 1: Write failing tests** — use `TestClient` with routes that use the new dependencies.

```python
# trading/tests/unit/test_identity_dependencies.py
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from api.identity.dependencies import resolve_identity, require_scope, Identity


def _make_app_with_route(dep):
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(dep)])
    async def protected():
        return {"ok": True}

    return app


def test_anonymous_caller_gets_anonymous_identity():
    # TODO: This test requires a mock IdentityStore on app.state.
    # Structure: instantiate app with an in-memory store containing
    # a known agent, call resolve_identity directly, assert Identity shape.
    pass  # implementation detail tested via integration below


def test_require_scope_rejects_anonymous_for_write_route(test_client_anon):
    resp = test_client_anon.get("/test/write-orders")
    assert resp.status_code == 403
    assert "write:orders" in resp.json()["detail"]


def test_require_scope_accepts_master_key(test_client_master_key):
    resp = test_client_master_key.get("/test/write-orders")
    assert resp.status_code == 200


def test_require_scope_accepts_verified_agent_with_matching_scope(test_client_verified_agent_with_write_orders):
    resp = test_client_verified_agent_with_write_orders.get("/test/write-orders")
    assert resp.status_code == 200


def test_require_scope_rejects_verified_agent_without_scope(test_client_verified_agent_without_write_orders):
    resp = test_client_verified_agent_without_write_orders.get("/test/write-orders")
    assert resp.status_code == 403


def test_unknown_token_returns_401(test_client_unknown_token):
    resp = test_client_unknown_token.get("/test/write-orders")
    assert resp.status_code == 401
```

(Fixtures set up a test app with registered test agents; details in `conftest.py`.)

- [ ] **Step 2: Run tests, verify failures.**

- [ ] **Step 3: Implement** `trading/api/identity/dependencies.py` per spec §3.D:

```python
# trading/api/identity/dependencies.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request

from .store import IdentityStore
from .tokens import hash_token, verify_token


@dataclass(frozen=True)
class Identity:
    name: str
    scopes: frozenset[str]
    tier: str
    agent_id: str | None = None


ANONYMOUS_IDENTITY = Identity(
    name="anonymous",
    scopes=frozenset(["read:arena", "read:kg"]),
    tier="anonymous",
)


def _get_store(request: Request) -> IdentityStore:
    store = getattr(request.app.state, "identity_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="identity store not initialized")
    return store


def _get_master_api_key(request: Request) -> str | None:
    config = getattr(request.app.state, "config", None)
    if not config:
        return None
    return getattr(config, "api_key", None)


async def resolve_identity(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    x_agent_token: Annotated[str | None, Header()] = None,
) -> Identity:
    """Resolve the caller's identity. Raises 401 on unknown X-Agent-Token."""
    # 1. Priority: X-Agent-Token (verified)
    if x_agent_token:
        store = _get_store(request)
        # We don't know the salt in advance, so scan-then-verify is O(n) over agents.
        # For small agent counts (< 10k), this is fine. For larger, add an index on
        # a second deterministic hash of the token (plain sha256, no salt) as a
        # lookup key, then verify the salted hash. Follow-up optimization.
        agents = await store.list_active()  # TODO: add this method
        for agent in agents:
            if verify_token(x_agent_token, agent.token_hash):
                return Identity(
                    name=agent.name,
                    scopes=frozenset(agent.scopes),
                    tier=agent.tier,
                    agent_id=agent.id,
                )
        raise HTTPException(status_code=401, detail="invalid X-Agent-Token")

    # 2. Fallback: X-API-Key (master)
    master_key = _get_master_api_key(request)
    if x_api_key and master_key and x_api_key == master_key:
        return Identity(
            name="master",
            scopes=frozenset(["admin", "*"]),
            tier="admin",
        )

    # 3. Default: anonymous
    return ANONYMOUS_IDENTITY


def require_scope(scope: str):
    async def checker(
        identity: Annotated[Identity, Depends(resolve_identity)],
    ) -> Identity:
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
    async def checker(
        identity: Annotated[Identity, Depends(resolve_identity)],
    ) -> Identity:
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

**Note the O(n) token scan.** For v1, acceptable. The follow-up optimization (dual-hash lookup) is in the spec §8 "out of scope" section.

- [ ] **Step 4: Add `IdentityStore.list_active()` to the store** — returns all non-revoked agents.

- [ ] **Step 5: Wire `IdentityStore` into `app.state` in `app.py`:**

```python
# trading/api/app.py (inside create_app or lifespan)
from api.identity.store import IdentityStore

# In lifespan:
app.state.identity_store = IdentityStore(pool=postgres_pool)
```

- [ ] **Step 6: Run tests, verify pass.**

- [ ] **Step 7: Commit**

```bash
git add trading/api/identity/dependencies.py trading/api/identity/store.py trading/api/app.py trading/tests/unit/test_identity_dependencies.py
git commit -m "feat(identity): add resolve_identity + require_scope FastAPI dependencies"
```

---

## Phase 5: Registration endpoints

### Task 5: Admin-only registration + self-inspection routes

**Files:**
- Create: `trading/api/routes/identity.py`
- Create: `trading/api/identity/schemas.py` (Pydantic request/response models)
- Modify: `trading/api/app.py` (register the router)
- Create: `trading/tests/integration/test_identity_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# trading/tests/integration/test_identity_routes.py
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_register_agent_returns_token_once(client_with_master_key):
    resp = client_with_master_key.post(
        "/api/v1/identity/agents",
        json={"name": "test-agent", "tier": "verified", "scopes": ["read:arena"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test-agent"
    assert data["token"].startswith("amu_")
    assert "warning" in data


@pytest.mark.integration
def test_me_endpoint_returns_identity(client_with_registered_agent):
    resp = client_with_registered_agent.get("/api/v1/identity/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "registered-test-agent"
    assert "read:arena" in data["scopes"]


@pytest.mark.integration
def test_me_endpoint_returns_anonymous_when_no_auth(anonymous_client):
    resp = anonymous_client.get("/api/v1/identity/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "anonymous"


@pytest.mark.integration
def test_revoke_agent_requires_admin(client_with_registered_agent):
    resp = client_with_registered_agent.post(
        "/api/v1/identity/agents/some-other-agent/revoke",
        json={"reason": "test"},
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_revoke_agent_then_token_rejected(client_with_master_key):
    # Register
    r1 = client_with_master_key.post(
        "/api/v1/identity/agents",
        json={"name": "to-revoke", "tier": "verified"},
    )
    token = r1.json()["token"]

    # Revoke
    r2 = client_with_master_key.post(
        "/api/v1/identity/agents/to-revoke/revoke",
        json={"reason": "test"},
    )
    assert r2.status_code == 200

    # Old token fails
    r3 = client_with_master_key.get(
        "/api/v1/identity/me",
        headers={"X-Agent-Token": token, "X-API-Key": ""},
    )
    assert r3.status_code == 401
```

- [ ] **Step 2: Run tests, verify failures.**

- [ ] **Step 3: Implement** `trading/api/identity/schemas.py`:

```python
# trading/api/identity/schemas.py
from pydantic import BaseModel, Field


class AgentRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=64)
    tier: str = Field(default="verified")
    scopes: list[str] | None = None
    contact_email: str | None = None
    moltbook_handle: str | None = None
    notes: str | None = None


class AgentRegistrationResponse(BaseModel):
    name: str
    id: str
    tier: str
    scopes: list[str]
    token: str
    warning: str


class AgentProfile(BaseModel):
    name: str
    scopes: list[str]
    tier: str


class RevocationRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
```

- [ ] **Step 4: Implement** `trading/api/routes/identity.py` per spec §3.F.

- [ ] **Step 5: Register the router in `app.py`:**

```python
from api.routes.identity import router as identity_router
app.include_router(identity_router)
```

- [ ] **Step 6: Run tests, verify pass.**

- [ ] **Step 7: Commit**

```bash
git add trading/api/identity/schemas.py trading/api/routes/identity.py trading/api/app.py trading/tests/integration/test_identity_routes.py
git commit -m "feat(identity): add registration, revocation, rotation, and /me endpoints"
```

---

## Phase 6: Route migration to scope gates

### Task 6: Migrate the 11 highest-risk routes to `require_scope`

**Files:**
- Modify: `trading/api/routes/orders.py` (2 routes)
- Modify: `trading/api/routes/trades.py` (1 route)
- Modify: `trading/api/routes/risk.py` (kill-switch + rules)
- Modify: `trading/api/routes/agents.py` (start, stop, scan, evolve)
- Modify: `trading/api/routes/competition.py` (bet, settle)

- [ ] **Step 1: Write integration tests for each migrated route** — one test per route, hitting with:
  - Master key → 200
  - Verified agent with the required scope → 200
  - Verified agent WITHOUT the required scope → 403
  - Anonymous → 403

Pattern:

```python
@pytest.mark.integration
def test_create_order_requires_write_orders_scope(
    client_master, client_agent_with_orders, client_agent_without_orders, anonymous_client
):
    payload = {"symbol": "BTC", "side": "BUY", "quantity": 0.001}

    assert client_master.post("/api/v1/orders", json=payload).status_code in (200, 201)
    assert client_agent_with_orders.post("/api/v1/orders", json=payload).status_code in (200, 201)
    assert client_agent_without_orders.post("/api/v1/orders", json=payload).status_code == 403
    assert anonymous_client.post("/api/v1/orders", json=payload).status_code == 403
```

Repeat for each of the 11 routes.

- [ ] **Step 2: Run tests, verify failures** (currently all use `verify_api_key` which passes master key but NOT the scoped agents).

- [ ] **Step 3: Migrate each route**

For `POST /api/v1/orders`:

```python
# trading/api/routes/orders.py
from api.identity.dependencies import require_scope, Identity
from fastapi import Depends

@router.post("")  # or "/orders"
async def create_order(
    req: CreateOrderRequest,
    identity: Identity = Depends(require_scope("write:orders")),
):
    # ... existing implementation
    pass
```

Remove the old `verify_api_key` dependency; the new `require_scope` handles both master key (via admin scope) and verified agents.

Repeat for the other 10 routes per the table in spec §3.G.

- [ ] **Step 4: Run tests, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add trading/api/routes/orders.py trading/api/routes/trades.py trading/api/routes/risk.py trading/api/routes/agents.py trading/api/routes/competition.py trading/tests/integration/test_route_scopes.py
git commit -m "feat(identity): migrate 11 highest-risk routes from verify_api_key to require_scope"
```

---

## Phase 7: Rate limiter integration

### Task 7: Update `defensive_perimeter` rate limiter bucket key

**Files:**
- Modify: `trading/api/middleware/limiter.py` (or wherever defensive_perimeter put the bucket key function)

**Blocked by:** `defensive_perimeter` Phase A implementation verified. Before starting, confirm the middleware's bucket key function exists and its current shape.

- [ ] **Step 1: Locate the bucket key function**

```bash
grep -rn "bucket_key\|rate_limit.*key" trading/api/middleware/ trading/api/ 2>&1 | head -10
```

- [ ] **Step 2: Update the bucket key function** per spec §3.H

```python
async def bucket_key(request: Request) -> str:
    # Cheap extraction without raising — middleware-safe
    x_agent_token = request.headers.get("X-Agent-Token")
    x_api_key = request.headers.get("X-API-Key")

    if x_agent_token:
        # Try to verify against the identity store
        store = getattr(request.app.state, "identity_store", None)
        if store:
            agents = await store.list_active()
            for agent in agents:
                if verify_token(x_agent_token, agent.token_hash):
                    return f"agent:{agent.name}"
        # Unknown/invalid token → fall through to IP-based
    elif x_api_key:
        config = getattr(request.app.state, "config", None)
        if config and x_api_key == getattr(config, "api_key", None):
            return "master:" + x_api_key[:8]  # first 8 chars only, for bucketing

    # Anonymous or unverified → IP
    return f"anon:{request.client.host}"
```

- [ ] **Step 3: Write a test** that rotates the `X-Agent-Token` value across fake names and confirms all requests go to the same IP bucket (not per-fake-name buckets).

- [ ] **Step 4: Run the test, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add trading/api/middleware/limiter.py trading/tests/integration/test_rate_limit_identity.py
git commit -m "feat(identity): update rate limiter bucket key to use verified agent name"
```

---

## Phase 8: Documentation + audit log integration

### Task 8: Document the Phase B closure + wire `@audit_event` to include `agent_id`

**Files:**
- Modify: `CLAUDE.md` (add "Agent Identity" section)
- Modify: `trading/utils/audit.py` (from defensive_perimeter — add `agent_id` from `resolve_identity`)
- Create: `docs/runbooks/agent-identity-operations.md`

- [ ] **Step 1: Update CLAUDE.md Working Boundaries**

Add under "Always do":
- **Use `require_scope(...)` for new write endpoints** — never layer auth via `verify_api_key` on new routes. The old dependency stays for back-compat but is deprecated for new code.

Add under "Ask first":
- **Adding a new scope** — the vocabulary in `conductor/tracks/agent_identity/spec.md` §3.C is load-bearing. New scopes need a spec update first.

- [ ] **Step 2: Update the `@audit_event` decorator from defensive_perimeter to pull `agent_id` from `resolve_identity`**

```python
# In the decorator body, after resolving the identity:
audit_data["actor_id"] = identity.name
audit_data["actor_type"] = "agent" if identity.agent_id else ("master" if identity.name == "master" else "anonymous")
```

- [ ] **Step 3: Write the operations runbook** — 1 page covering: how to register an agent (curl example), how to revoke, how to rotate, what to do if the master key leaks, common scope patterns.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md trading/utils/audit.py docs/runbooks/agent-identity-operations.md
git commit -m "docs(identity): CLAUDE.md boundaries, audit_event agent_id, operations runbook"
```

---

## Quality Gates (from spec §7, restated)

- [ ] Migration applies cleanly (Task 1)
- [ ] Registration flow works end-to-end (Task 5)
- [ ] Revocation takes effect within 60s (Task 5)
- [ ] Scope enforcement on migrated routes (Task 6)
- [ ] Back-compat: master key still works on all migrated routes (Task 6)
- [ ] Unknown token returns 401 (Task 4)
- [ ] Anonymous tier default scopes (Task 4)
- [ ] Rate limiter bucket key uses verified name (Task 7)
- [ ] No secrets in error messages (Task 4, 5)
- [ ] Audit log captures identity events (Task 3, 5)
- [ ] `@audit_event` includes `agent_id` (Task 8)

## Commit strategy

8 logical commits across 8 phases. Each commit is independently buildable and testable. Task 7 requires `defensive_perimeter` Phase A landed AND verified. Tasks 1-6 can land on a feature branch before Task 7 if the Phase A verification slips.
