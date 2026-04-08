-- scripts/competition-tables.sql
-- Competition system tables for Arena Alpha

CREATE TABLE IF NOT EXISTS competitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL CHECK (type IN ('agent', 'miner', 'provider')),
    name VARCHAR(100) NOT NULL,
    ref_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'shadow', 'retired')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(type, ref_id)
);

CREATE TABLE IF NOT EXISTS elo_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    elo INTEGER DEFAULT 1000,
    tier VARCHAR(20) DEFAULT 'silver' CHECK (tier IN ('bronze', 'silver', 'gold', 'diamond')),
    matches_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset)
);
CREATE INDEX IF NOT EXISTS idx_elo_ratings_leaderboard
    ON elo_ratings(asset, elo DESC);

CREATE TABLE IF NOT EXISTS elo_history (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    elo INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL,
    elo_delta INTEGER DEFAULT 0,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_elo_history_lookup
    ON elo_history(competitor_id, asset, recorded_at DESC);

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    competitor_a_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    competitor_b_id UUID REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    window VARCHAR(10) NOT NULL,
    winner_id UUID,
    score_a DECIMAL(10, 6),
    score_b DECIMAL(10, 6),
    elo_delta_a INTEGER,
    elo_delta_b INTEGER,
    match_type VARCHAR(20) CHECK (match_type IN ('baseline', 'pairwise')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_matches_lookup
    ON matches(competitor_a_id, competitor_b_id, created_at DESC);

CREATE TABLE IF NOT EXISTS achievements (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    achievement_type VARCHAR(50) NOT NULL,
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_achievements_lookup
    ON achievements(competitor_id, achievement_type);

CREATE TABLE IF NOT EXISTS streaks (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    streak_type VARCHAR(30) NOT NULL,
    current_count INTEGER DEFAULT 0,
    best_count INTEGER DEFAULT 0,
    last_event_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset, streak_type)
);

CREATE TABLE IF NOT EXISTS competition_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    matches_created INTEGER DEFAULT 0,
    achievements_awarded INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);
