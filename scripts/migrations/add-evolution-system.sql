CREATE TABLE IF NOT EXISTS agent_mutations (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    trait VARCHAR(50) NOT NULL,
    rarity VARCHAR(20) NOT NULL DEFAULT 'common',
    bonus_multiplier DECIMAL(3,2) NOT NULL DEFAULT 1.1,
    level_obtained INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_mutations_agent ON agent_mutations(agent_id);
CREATE INDEX idx_agent_mutations_rarity ON agent_mutations(rarity);

CREATE TABLE IF NOT EXISTS agent_lineage (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    parent_a_id UUID REFERENCES competitors(id),
    parent_b_id UUID REFERENCES competitors(id),
    generation INTEGER NOT NULL DEFAULT 0,
    breeding_count INTEGER NOT NULL DEFAULT 0,
    last_breed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_agent_lineage_agent ON agent_lineage(agent_id);
CREATE INDEX idx_agent_lineage_parents ON agent_lineage(parent_a_id, parent_b_id);
