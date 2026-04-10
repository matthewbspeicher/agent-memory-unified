-- Arena system tables for escape room puzzles
-- Adds gyms, challenges, sessions, turns, and matches

CREATE TABLE IF NOT EXISTS arena_gyms (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    room_type VARCHAR(50) NOT NULL DEFAULT 'deterministic',
    difficulty INTEGER NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 10),
    xp_reward DECIMAL(10,2) NOT NULL DEFAULT 100.0,
    max_turns INTEGER NOT NULL DEFAULT 20,
    icon VARCHAR(50) NOT NULL DEFAULT '🏛️',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_challenges (
    id VARCHAR(255) PRIMARY KEY,
    gym_id VARCHAR(255) NOT NULL REFERENCES arena_gyms(id),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    difficulty INTEGER NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 10),
    room_type VARCHAR(50) NOT NULL DEFAULT 'deterministic',
    initial_state JSONB NOT NULL DEFAULT '{}',
    tools JSONB NOT NULL DEFAULT '["fs_read", "fs_list", "exec_python", "db_query", "db_schema", "state", "submit_flag"]',
    max_turns INTEGER NOT NULL DEFAULT 20,
    xp_reward DECIMAL(10,2) NOT NULL DEFAULT 100.0,
    flag_hash VARCHAR(255),
    flag_hint TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arena_sessions (
    id VARCHAR(255) PRIMARY KEY,
    challenge_id VARCHAR(255) NOT NULL REFERENCES arena_challenges(id),
    agent_id VARCHAR(255) NOT NULL,
    current_state VARCHAR(50) NOT NULL DEFAULT 'start',
    inventory JSONB NOT NULL DEFAULT '[]',
    turn_count INTEGER NOT NULL DEFAULT 0,
    score DECIMAL(10,2) NOT NULL DEFAULT 0.0,
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'failed', 'abandoned')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS arena_turns (
    id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES arena_sessions(id),
    turn_number INTEGER NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    tool_input JSONB NOT NULL DEFAULT '{}',
    tool_output TEXT,
    score_delta DECIMAL(10,2) NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(session_id, turn_number)
);

CREATE TABLE IF NOT EXISTS arena_matches (
    id VARCHAR(255) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES arena_sessions(id),
    bet_pool_id VARCHAR(255),
    challenge_id VARCHAR(255) NOT NULL REFERENCES arena_challenges(id),
    agent_id VARCHAR(255) NOT NULL,
    final_score DECIMAL(10,2),
    final_status VARCHAR(50),
    xp_earned DECIMAL(10,2) DEFAULT 0.0,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_arena_challenges_gym ON arena_challenges(gym_id);
CREATE INDEX IF NOT EXISTS idx_arena_challenges_difficulty ON arena_challenges(difficulty);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_challenge ON arena_sessions(challenge_id);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_agent ON arena_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_status ON arena_sessions(status);
CREATE INDEX IF NOT EXISTS idx_arena_turns_session ON arena_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_arena_matches_session ON arena_matches(session_id);
CREATE INDEX IF NOT EXISTS idx_arena_matches_agent ON arena_matches(agent_id);

-- Seed default gyms with correct room types
INSERT INTO arena_gyms (id, name, description, room_type, difficulty, xp_reward, max_turns, icon)
VALUES
    ('gym-data-explorer', 'Data Explorer', 'Query databases to find hidden information', 'deterministic', 1, 50.0, 15, 'DATA'),
    ('gym-cipher-master', 'Cipher Master', 'Decode encrypted messages and break cryptographic puzzles', 'cipher', 3, 150.0, 20, 'CIPHER'),
    ('gym-system-admin', 'System Administrator', 'Navigate file systems and manage server configurations', 'filesystem', 5, 250.0, 25, 'SYS'),
    ('gym-code-breaker', 'Code Breaker', 'Reverse engineer and analyze complex code structures', 'deterministic', 7, 400.0, 30, 'CODE'),
    ('gym-final-arena', 'The Final Arena', 'Ultimate challenge combining all skills', 'deterministic', 10, 1000.0, 50, 'FINAL')
ON CONFLICT (id) DO NOTHING;

-- Seed challenges for Data Explorer gym (database puzzles)
INSERT INTO arena_challenges (id, gym_id, name, description, difficulty, room_type, initial_state, tools, max_turns, xp_reward, flag_hint)
VALUES
    ('challenge-db-1', 'gym-data-explorer', 'Find the API Key', 'A user left their API key somewhere in the database. Find it.', 1, 'deterministic',
     '{"tables": {"users": [{"id": 1, "name": "Alice", "email": "alice@example.com"}, {"id": 2, "name": "Bob", "email": "bob@example.com"}], "api_keys": [{"user_id": 1, "key": "FLAG{alice_secret_123}"}]}}',
     '["db_schema", "db_query", "submit_flag"]',
     15, 50.0, 'The key is in the api_keys table'),
    ('challenge-db-2', 'gym-data-explorer', 'Join the Tables', 'Find the transaction linked to a specific user through a JOIN.', 2, 'deterministic',
     '{"tables": {"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}], "accounts": [{"id": 100, "user_id": 1, "balance": 1000}, {"id": 200, "user_id": 2, "balance": 500}], "transactions": [{"id": 1, "account_id": 100, "memo": "Regular deposit"}, {"id": 2, "account_id": 200, "memo": "FLAG{bob_transaction_xyz}"}]}}',
     '["db_schema", "db_query", "submit_flag"]',
     20, 75.0, 'Find Bob''s transaction')
ON CONFLICT (id) DO NOTHING;

-- Seed challenges for Cipher Master gym (crypto puzzles)
INSERT INTO arena_challenges (id, gym_id, name, description, difficulty, room_type, initial_state, tools, max_turns, xp_reward, flag_hint, flag_hash)
VALUES
    ('challenge-cipher-1', 'gym-cipher-master', 'ROT13 Basics', 'Decode the ROT13 encoded message to find the flag.', 1, 'cipher',
     '{"files": {"message.txt": "SYNT{ebgngr_13_frrhf}", "hint.txt": "ROT13 shifts each letter by 13 positions"}, "flag": "FLAG{rot13_secrets}", "cipher_type": "rot13"}',
     '["fs_read", "exec_python", "submit_flag"]',
     15, 100.0, 'ROT13 shifts letters by 13', NULL),
    ('challenge-cipher-2', 'gym-cipher-master', 'Caesar Cipher', 'The shift value is hidden somewhere. Find it and decrypt.', 3, 'cipher',
     '{"files": {"encoded.txt": "FLAG{caesar_was_here}", "note.txt": "Shift: 7"}, "flag": "FLAG{caesar_was_here}", "cipher_type": "caesar"}',
     '["fs_read", "exec_python", "submit_flag"]',
     20, 200.0, 'Check the note file for the shift value', NULL)
ON CONFLICT (id) DO NOTHING;

-- Seed challenges for System Admin gym (filesystem puzzles)
INSERT INTO arena_challenges (id, gym_id, name, description, difficulty, room_type, initial_state, tools, max_turns, xp_reward, flag_hint)
VALUES
    ('challenge-fs-1', 'gym-system-admin', 'Hidden Directory', 'Find the flag hidden in a secret directory.', 1, 'filesystem',
     '{"files": {"readme.txt": "Welcome to the system. Look around carefully.", "config.yaml": "server: localhost"}, "hidden_files": {".secret/flag.txt": "FLAG{hidden_in_dotdir}"}, "flag": "FLAG{hidden_in_dotdir}"}',
     '["fs_list", "fs_read", "submit_flag"]',
     15, 150.0, 'Some directories start with a dot'),
    ('challenge-fs-2', 'gym-system-admin', 'File Metadata', 'Analyze file contents and relationships to find the flag.', 3, 'filesystem',
     '{"files": {"notes.txt": "The flag pieces are in files 1 through 3", "part1.txt": "FLAG{file_", "part2.txt": "system_", "part3.txt": "master}"}, "hidden_files": {}, "flag": "FLAG{file_system_master}"}',
     '["fs_list", "fs_read", "exec_python", "submit_flag"]',
     20, 250.0, 'Combine the parts to form the flag')
ON CONFLICT (id) DO NOTHING;
