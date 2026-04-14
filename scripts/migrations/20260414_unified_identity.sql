-- scripts/migrations/20260414_unified_identity.sql
CREATE TYPE platform_tier AS ENUM ('explorer', 'trader', 'enterprise', 'whale');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    tier platform_tier DEFAULT 'explorer',
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE identity.agents ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE identity.agents ADD COLUMN tier TEXT;
