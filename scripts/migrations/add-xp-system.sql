-- scripts/migrations/add-xp-system.sql
-- Migration: Add XP and leveling system to competition tables

-- Add xp column to elo_ratings (default 0 for existing rows)
ALTER TABLE elo_ratings 
    ADD COLUMN IF NOT EXISTS xp INTEGER DEFAULT 0;

-- Create xp_history table for tracking XP awards
CREATE TABLE IF NOT EXISTS xp_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    source VARCHAR(30) NOT NULL,  -- XpSource enum value
    amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_xp_history_lookup
    ON xp_history(competitor_id, asset, created_at DESC);
