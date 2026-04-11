-- Add streak tracking columns to performance_snapshots
-- Created: 2026-04-10

ALTER TABLE performance_snapshots 
ADD COLUMN IF NOT EXISTS consecutive_losses INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS max_consecutive_losses INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS consecutive_wins INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS max_consecutive_wins INTEGER DEFAULT 0;
