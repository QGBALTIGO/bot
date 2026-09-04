CREATE TABLE IF NOT EXISTS source_v2_pass_state (
    user_id BIGINT NOT NULL,
    season_id TEXT NOT NULL,
    pass_type TEXT NOT NULL DEFAULT 'free'
        CHECK (pass_type IN ('free', 'premium', 'elite')),
    bank_coins BIGINT NOT NULL DEFAULT 0 CHECK (bank_coins >= 0),
    activated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, season_id)
);

CREATE TABLE IF NOT EXISTS source_v2_pass_claims (
    user_id BIGINT NOT NULL,
    season_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 100),
    pass_type_at_claim TEXT NOT NULL
        CHECK (pass_type_at_claim IN ('free', 'premium', 'elite')),
    coins_awarded BIGINT NOT NULL DEFAULT 0 CHECK (coins_awarded >= 0),
    eggs_awarded INTEGER NOT NULL DEFAULT 0 CHECK (eggs_awarded >= 0),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, season_id, level)
);

CREATE TABLE IF NOT EXISTS source_v2_eggs (
    egg_id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('common', 'gold', 'void', 'rare', 'legendary', 'celestial')),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'fresh'
        CHECK (status IN ('fresh', 'incubating', 'ready', 'hatched', 'sold', 'fused')),
    corrupted BOOLEAN NOT NULL DEFAULT FALSE,
    source_type TEXT NOT NULL DEFAULT 'pass',
    source_id TEXT,
    incubation_started_at TIMESTAMPTZ,
    incubation_ends_at TIMESTAMPTZ,
    hatched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_v2_eggs_user_status
    ON source_v2_eggs (user_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS source_v2_pass_orders (
    order_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    season_id TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('premium', 'elite')),
    current_tier TEXT NOT NULL CHECK (current_tier IN ('free', 'premium', 'elite')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'XTR' CHECK (currency = 'XTR'),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'superseded', 'invoice_failed', 'precheckout', 'fulfilling', 'fulfilled', 'expired')),
    invoice_url TEXT,
    precheckout_query_id TEXT,
    telegram_payment_charge_id TEXT UNIQUE,
    provider_payment_charge_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    precheckout_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    fulfilled_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_v2_pass_orders_user
    ON source_v2_pass_orders (user_id, season_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_v2_pass_orders_status
    ON source_v2_pass_orders (status, expires_at);
