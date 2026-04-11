-- Portfolio state persistence for kill switch HWM tracking
-- Created: 2026-04-10

CREATE TABLE IF NOT EXISTS portfolio_state (
    key TEXT PRIMARY KEY,
    high_water_mark TEXT NOT NULL,
    triggered INTEGER NOT NULL DEFAULT 0,
    triggered_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_state_updated
ON portfolio_state(updated_at DESC);
