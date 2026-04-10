CREATE TABLE IF NOT EXISTS mission_progress (
    id UUID PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    mission_id VARCHAR(50) NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    target INTEGER NOT NULL DEFAULT 1,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    claimed BOOLEAN NOT NULL DEFAULT FALSE,
    xp_awarded INTEGER NOT NULL DEFAULT 0,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(competitor_id, mission_id, period_start)
);

CREATE INDEX idx_mission_progress_competitor ON mission_progress(competitor_id);
CREATE INDEX idx_mission_progress_period ON mission_progress(period_end);
CREATE INDEX idx_mission_progress_claimable ON mission_progress(competitor_id, completed, claimed);
