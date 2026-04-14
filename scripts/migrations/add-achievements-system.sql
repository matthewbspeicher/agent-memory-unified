-- scripts/migrations/add-achievements-system.sql
-- Migration: Add per-agent achievement persistence

CREATE TABLE IF NOT EXISTS agent_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    achievement_id TEXT NOT NULL,
    unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
    context TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(agent_name, achievement_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_achievements_agent
    ON agent_achievements(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_achievements_unlocked
    ON agent_achievements(achievement_id, unlocked_at DESC);
