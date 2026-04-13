import pytest
import asyncpg
from api.identity.store import IdentityStore
from api.identity.tokens import hash_token


@pytest.fixture
async def identity_store(postgres_dsn):
    pool = await asyncpg.connect(postgres_dsn)
    try:
        await pool.execute("TRUNCATE identity.agents, identity.audit_log CASCADE")
    finally:
        await pool.close()

    pool = await asyncpg.create_pool(postgres_dsn, min_size=1, max_size=5)
    store = IdentityStore(pool)
    yield store
    await pool.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_lookup_by_name(identity_store):
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
async def test_lookup_by_token_hash_returns_agent(identity_store):
    token = "amu_test_lookup"
    h = hash_token(token)
    await identity_store.create(
        name="lookup-agent", token_hash=h, scopes=[], tier="verified", created_by="t"
    )
    fetched = await identity_store.get_by_token_hash(h)
    assert fetched is not None
    assert fetched.name == "lookup-agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoked_agent_not_returned_by_lookups(identity_store):
    h = hash_token("amu_to_revoke")
    await identity_store.create(
        name="revoke-me", token_hash=h, scopes=[], tier="verified", created_by="t"
    )
    await identity_store.revoke(name="revoke-me", reason="test", actor="t")
    assert await identity_store.get_by_name("revoke-me") is None
    assert await identity_store.get_by_token_hash(h) is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_log_records_creation_and_revocation(identity_store):
    h = hash_token("amu_audit")
    await identity_store.create(
        name="audit-agent", token_hash=h, scopes=[], tier="verified", created_by="t"
    )
    await identity_store.audit(
        event="created", agent_name="audit-agent", actor="t", details={}
    )
    await identity_store.revoke(name="audit-agent", reason="test", actor="t")
    await identity_store.audit(
        event="revoked", agent_name="audit-agent", actor="t", details={"reason": "test"}
    )

    events = await identity_store.get_audit_log(agent_name="audit-agent")
    assert len(events) >= 2
    event_types = {e["event"] for e in events}
    assert "created" in event_types
    assert "revoked" in event_types
