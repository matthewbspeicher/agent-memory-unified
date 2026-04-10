CREATE TABLE IF NOT EXISTS match_bets (
    id UUID PRIMARY KEY,
    match_id UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    better_id VARCHAR(255) NOT NULL,
    predicted_winner UUID NOT NULL REFERENCES competitors(id),
    amount INTEGER NOT NULL CHECK (amount >= 10 AND amount <= 1000),
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    payout INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    settled_at TIMESTAMPTZ
);

CREATE INDEX idx_match_bets_match ON match_bets(match_id);
CREATE INDEX idx_match_bets_better ON match_bets(better_id);
CREATE INDEX idx_match_bets_status ON match_bets(match_id, status);
