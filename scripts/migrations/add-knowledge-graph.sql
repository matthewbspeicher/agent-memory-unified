-- Migration: Add Knowledge Graph schema and tables
-- Target: PostgreSQL

CREATE SCHEMA IF NOT EXISTS kg;

CREATE TABLE IF NOT EXISTS kg.kg_entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT DEFAULT 'unknown',
    properties TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kg.kg_triples (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL REFERENCES kg.kg_entities(id),
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    properties TEXT DEFAULT '{}',
    invalidation_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kg_triples_subject ON kg.kg_triples(subject);
CREATE INDEX IF NOT EXISTS idx_kg_triples_object ON kg.kg_triples(object);
CREATE INDEX IF NOT EXISTS idx_kg_triples_predicate ON kg.kg_triples(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_triples_validity ON kg.kg_triples(valid_from, valid_to);

-- Audit Logging integration points (v2 spec requirement)
CREATE TABLE IF NOT EXISTS kg.audit_log (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE', 'INVALIDATE'
    entity_id TEXT,
    triple_id TEXT,
    old_data TEXT,
    new_data TEXT,
    actor_id TEXT, -- agent_name or 'system'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
