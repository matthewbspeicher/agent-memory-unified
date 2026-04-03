-- 003_observability.sql
-- Run once in Supabase SQL editor (or via supabase CLI: supabase db push)

CREATE TABLE IF NOT EXISTS system_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    level       TEXT NOT NULL CHECK (level IN ('critical', 'warning', 'info')),
    event_type  TEXT NOT NULL,
    agent_name  TEXT,
    message     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_system_events_level      ON system_events (level);
CREATE INDEX IF NOT EXISTS idx_system_events_agent      ON system_events (agent_name);
CREATE INDEX IF NOT EXISTS idx_system_events_timestamp  ON system_events (timestamp DESC);

CREATE TABLE IF NOT EXISTS trade_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    action          TEXT NOT NULL CHECK (action IN ('buy', 'sell', 'short', 'cover')),
    fill_price      DECIMAL NOT NULL,
    expected_price  DECIMAL NOT NULL,
    slippage_bps    INTEGER NOT NULL,
    commission      DECIMAL NOT NULL DEFAULT 0,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_events_agent      ON trade_events (agent_name);
CREATE INDEX IF NOT EXISTS idx_trade_events_timestamp  ON trade_events (timestamp DESC);

CREATE TABLE IF NOT EXISTS agent_heartbeats (
    agent_name   TEXT PRIMARY KEY,
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    status       TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'idle', 'stalled')),
    cycle_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name    TEXT NOT NULL,
    sharpe        DECIMAL NOT NULL DEFAULT 0,
    win_rate      DECIMAL NOT NULL DEFAULT 0,
    max_drawdown  DECIMAL NOT NULL DEFAULT 0,
    trade_count   INTEGER NOT NULL DEFAULT 0,
    snapshot_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metric_snapshots_agent  ON metric_snapshots (agent_name);
CREATE INDEX IF NOT EXISTS idx_metric_snapshots_time   ON metric_snapshots (snapshot_at DESC);
