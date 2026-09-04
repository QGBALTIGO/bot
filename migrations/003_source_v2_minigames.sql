CREATE TABLE IF NOT EXISTS source_v2_minigame_energy (
    user_id BIGINT PRIMARY KEY,
    energy INTEGER NOT NULL DEFAULT 5 CHECK (energy >= 0 AND energy <= 5),
    last_recharge_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_v2_minigame_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    game_type TEXT NOT NULL CHECK (game_type IN ('cipher_match', 'nexus_wheel')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'submitted', 'expired', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    submitted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_source_v2_minigame_sessions_user
    ON source_v2_minigame_sessions (user_id, game_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_v2_minigame_sessions_expiry
    ON source_v2_minigame_sessions (status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_v2_minigame_active
    ON source_v2_minigame_sessions (user_id, game_type)
    WHERE status = 'active';
