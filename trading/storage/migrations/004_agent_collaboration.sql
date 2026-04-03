-- 004_agent_collaboration.sql

CREATE TABLE IF NOT EXISTS agent_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_agent TEXT NOT NULL,
    target_agent TEXT,
    signal_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    expires_at TIMESTAMPTZ NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_signals_source ON agent_signals (source_agent);
CREATE INDEX IF NOT EXISTS idx_agent_signals_target ON agent_signals (target_agent);
CREATE INDEX IF NOT EXISTS idx_agent_signals_timestamp ON agent_signals (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_signals_expires ON agent_signals (expires_at);
