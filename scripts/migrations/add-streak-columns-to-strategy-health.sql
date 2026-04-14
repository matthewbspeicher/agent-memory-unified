-- Add streak tracking columns to strategy_health table
-- These duplicate the streak data from performance_snapshots for faster health queries

ALTER TABLE strategy_health ADD COLUMN consecutive_losses INTEGER NOT NULL DEFAULT 0;
ALTER TABLE strategy_health ADD COLUMN max_consecutive_losses INTEGER NOT NULL DEFAULT 0;
ALTER TABLE strategy_health ADD COLUMN consecutive_wins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE strategy_health ADD COLUMN max_consecutive_wins INTEGER NOT NULL DEFAULT 0;
