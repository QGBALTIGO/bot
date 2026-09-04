CREATE TABLE IF NOT EXISTS source_v2_achievement_unlocks (
    user_id BIGINT NOT NULL,
    achievement_id TEXT NOT NULL,
    title TEXT,
    reward_xp INTEGER NOT NULL DEFAULT 0 CHECK (reward_xp >= 0),
    reward_coins BIGINT NOT NULL DEFAULT 0 CHECK (reward_coins >= 0),
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, achievement_id)
);

CREATE INDEX IF NOT EXISTS idx_source_v2_achievement_unlocks_time
    ON source_v2_achievement_unlocks (unlocked_at DESC);

CREATE TABLE IF NOT EXISTS source_v2_titles (
    user_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'achievement',
    source_id TEXT,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, title)
);

CREATE INDEX IF NOT EXISTS idx_source_v2_titles_user_time
    ON source_v2_titles (user_id, unlocked_at DESC);

CREATE TABLE IF NOT EXISTS source_v2_quest_claims (
    user_id BIGINT NOT NULL,
    period_key TEXT NOT NULL,
    quest_id TEXT NOT NULL,
    reward_xp INTEGER NOT NULL DEFAULT 0 CHECK (reward_xp >= 0),
    reward_coins BIGINT NOT NULL DEFAULT 0 CHECK (reward_coins >= 0),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, period_key, quest_id)
);

CREATE INDEX IF NOT EXISTS idx_source_v2_quest_claims_user_time
    ON source_v2_quest_claims (user_id, claimed_at DESC);
