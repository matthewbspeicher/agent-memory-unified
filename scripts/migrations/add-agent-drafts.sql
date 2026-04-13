-- scripts/migrations/add-agent-drafts.sql

CREATE TABLE IF NOT EXISTS identity.agent_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    system_prompt   TEXT NOT NULL,
    model           TEXT NOT NULL DEFAULT 'gpt-4o',
    hyperparameters JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'draft',
    backtest_results JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_drafts_status ON identity.agent_drafts(status);
CREATE INDEX IF NOT EXISTS idx_agent_drafts_created ON identity.agent_drafts(created_at DESC);
