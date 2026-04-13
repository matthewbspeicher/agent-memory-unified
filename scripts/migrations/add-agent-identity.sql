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
