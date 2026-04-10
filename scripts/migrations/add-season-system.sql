CREATE TABLE IF NOT EXISTS seasons (
    id UUID PRIMARY KEY,
    number INTEGER NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    total_participants INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_seasons_ends ON seasons(ends_at);
CREATE INDEX idx_seasons_number ON seasons(number DESC);

INSERT INTO seasons (id, number, name, started_at, ends_at)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    1,
    'Season 1',
    NOW() - INTERVAL '30 days',
    NOW() + INTERVAL '60 days'
) ON CONFLICT (number) DO NOTHING;
