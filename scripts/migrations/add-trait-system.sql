-- scripts/migrations/add-trait-system.sql
-- Migration: Add trait unlock and loadout system to competition tables

-- Create unlocked_traits table for tracking which traits each competitor has unlocked
CREATE TABLE IF NOT EXISTS unlocked_traits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    trait VARCHAR(30) NOT NULL,  -- AgentTrait enum value
    unlocked_at_level INTEGER NOT NULL,
    unlocked_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, trait)
);
CREATE INDEX IF NOT EXISTS idx_unlocked_traits_competitor
    ON unlocked_traits(competitor_id);

-- Create trait_loadout table for active trait slots (max 3 per competitor/asset)
CREATE TABLE IF NOT EXISTS trait_loadout (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    asset VARCHAR(10) NOT NULL,
    primary_trait VARCHAR(30),   -- AgentTrait enum value or NULL
    secondary_trait VARCHAR(30), -- AgentTrait enum value or NULL
    tertiary_trait VARCHAR(30),  -- AgentTrait enum value or NULL
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(competitor_id, asset)
);
CREATE INDEX IF NOT EXISTS idx_trait_loadout_competitor
    ON trait_loadout(competitor_id, asset);
