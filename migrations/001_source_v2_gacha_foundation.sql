CREATE TABLE IF NOT EXISTS character_art_assets (
    id BIGSERIAL PRIMARY KEY,
    character_id BIGINT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_url TEXT,
    image_url TEXT NOT NULL,
    storage_url TEXT,
    telegram_file_id TEXT,
    width INTEGER,
    height INTEGER,
    aspect_ratio NUMERIC(10, 6),
    sha256 TEXT,
    perceptual_hash TEXT,
    variant TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL DEFAULT 'approved'
        CHECK (status IN ('pending', 'approved', 'rejected', 'archived')),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    source_credit TEXT,
    source_license TEXT,
    reviewed_by BIGINT,
    reviewed_at TIMESTAMPTZ,
    created_by BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (character_id, image_url)
);

CREATE INDEX IF NOT EXISTS idx_character_art_assets_character
    ON character_art_assets (character_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_character_art_assets_status
    ON character_art_assets (status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_character_art_assets_primary
    ON character_art_assets (character_id)
    WHERE is_primary = TRUE AND status = 'approved';

CREATE TABLE IF NOT EXISTS gacha_rarities (
    slug TEXT PRIMARY KEY,
    seal_rarity_id INTEGER UNIQUE,
    emoji TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    tier INTEGER NOT NULL DEFAULT 1 CHECK (tier > 0),
    spawn_weight INTEGER NOT NULL DEFAULT 0 CHECK (spawn_weight >= 0),
    active_spawn_weight INTEGER NOT NULL DEFAULT 0 CHECK (active_spawn_weight >= 0),
    shop_weight INTEGER NOT NULL DEFAULT 0 CHECK (shop_weight >= 0),
    claim_weight INTEGER NOT NULL DEFAULT 0 CHECK (claim_weight >= 0),
    base_reward BIGINT NOT NULL DEFAULT 0 CHECK (base_reward >= 0),
    pity_threshold INTEGER NOT NULL DEFAULT 0 CHECK (pity_threshold >= 0),
    craft_cost BIGINT NOT NULL DEFAULT 0 CHECK (craft_cost >= 0),
    requires_fragments BOOLEAN NOT NULL DEFAULT FALSE,
    fragments_required INTEGER NOT NULL DEFAULT 0 CHECK (fragments_required >= 0),
    shop_price BIGINT NOT NULL DEFAULT 0 CHECK (shop_price >= 0),
    stock_limit INTEGER NOT NULL DEFAULT 0 CHECK (stock_limit >= 0),
    sell_price BIGINT NOT NULL DEFAULT 0 CHECK (sell_price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed the public Seal rarity catalog as the initial Source v2 content model.
-- Pity/crafting fields deliberately stay disabled until the balancing migration.
INSERT INTO gacha_rarities
    (slug, seal_rarity_id, emoji, name, tier, spawn_weight, active_spawn_weight,
     shop_weight, claim_weight, shop_price, stock_limit, sell_price)
VALUES
    ('common', 1, '⚪', 'Common', 1, 360, 280, 25, 60, 1, 50, 50),
    ('medium', 2, '🟢', 'Medium', 2, 240, 220, 20, 30, 2, 40, 100),
    ('rare', 3, '🟠', 'Rare', 3, 110, 130, 15, 9, 4, 30, 250),
    ('legendary', 4, '🟡', 'Legendary', 5, 50, 70, 10, 1, 6, 20, 600),
    ('cosmic', 5, '💠', 'Cosmic', 6, 25, 35, 8, 0, 10, 15, 1200),
    ('exclusive', 6, '💮', 'Exclusive', 7, 4, 6, 6, 0, 30, 10, 2500),
    ('limited-edition', 7, '🔮', 'Limited Edition', 8, 2, 3, 5, 0, 45, 10, 5000),
    ('royal', 8, '🫧', 'Royal', 9, 1, 2, 4, 0, 60, 5, 10000),
    ('celestial', 10, '🎐', 'Celestial', 10, 1, 1, 2, 0, 80, 2, 20000),
    ('cinematic', 11, '🎞️', 'Cinematic', 10, 1, 1, 2, 0, 80, 2, 30000),
    ('prestige', 12, '🪽', 'Prestige', 11, 1, 1, 1, 0, 100, 1, 40000),
    ('winter', 13, '❄️', 'Winter', 6, 12, 15, 6, 0, 15, 10, 1500),
    ('summer', 14, '☀️', 'Summer', 6, 12, 15, 6, 0, 15, 10, 1500),
    ('valentine', 15, '💖', 'Valentine', 7, 5, 8, 5, 0, 25, 10, 2000),
    ('halloween', 16, '🎃', 'Halloween', 7, 5, 8, 5, 0, 25, 10, 2000),
    ('epic', 19, '🟣', 'Epic', 4, 120, 140, 20, 0, 3, 40, 150),
    ('immortal', 20, '🧬', 'Immortal', 6, 25, 35, 8, 0, 10, 15, 1200),
    ('eternal', 21, '🌌', 'Eternal', 7, 3, 4, 6, 0, 35, 10, 2500),
    ('arcane', 22, '🌀', 'Arcane', 8, 2, 3, 5, 0, 45, 10, 5000),
    ('mythical', 23, '💎', 'Mythical', 9, 1, 2, 3, 0, 60, 5, 12000),
    ('divine', 24, '✨', 'Divine', 10, 1, 1, 2, 0, 80, 2, 30000),
    ('astral', 25, '🌠', 'Astral', 11, 1, 1, 1, 0, 100, 1, 40000),
    ('radiant', 26, '🌟', 'Radiant', 7, 8, 12, 5, 0, 20, 10, 2000),
    ('eclipse', 27, '🌑', 'Eclipse', 9, 2, 3, 4, 0, 50, 8, 8000),
    ('seraph', 28, '😇', 'Seraph', 11, 1, 1, 1, 0, 90, 1, 35000)
ON CONFLICT (slug) DO NOTHING;

CREATE TABLE IF NOT EXISTS gacha_sets (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    buff_type TEXT,
    buff_value INTEGER NOT NULL DEFAULT 0,
    reward_points INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS character_gacha_meta (
    character_id BIGINT PRIMARY KEY,
    rarity_slug TEXT NOT NULL DEFAULT 'common'
        REFERENCES gacha_rarities(slug) ON UPDATE CASCADE,
    set_id BIGINT REFERENCES gacha_sets(id) ON DELETE SET NULL,
    power_level INTEGER NOT NULL DEFAULT 0 CHECK (power_level >= 0),
    event_tag TEXT NOT NULL DEFAULT 'standard',
    is_spawnable BOOLEAN NOT NULL DEFAULT TRUE,
    is_shop_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_character_gacha_meta_rarity
    ON character_gacha_meta (rarity_slug, character_id);
CREATE INDEX IF NOT EXISTS idx_character_gacha_meta_set
    ON character_gacha_meta (set_id, character_id);

CREATE TABLE IF NOT EXISTS user_gacha_pity (
    user_id BIGINT NOT NULL,
    banner_key TEXT NOT NULL DEFAULT 'standard',
    pity_count INTEGER NOT NULL DEFAULT 0 CHECK (pity_count >= 0),
    guaranteed_high_rarity BOOLEAN NOT NULL DEFAULT FALSE,
    last_high_rarity_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, banner_key)
);

CREATE TABLE IF NOT EXISTS user_character_fragments (
    user_id BIGINT NOT NULL,
    character_id BIGINT NOT NULL,
    fragments INTEGER NOT NULL DEFAULT 0 CHECK (fragments >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, character_id)
);

CREATE INDEX IF NOT EXISTS idx_user_character_fragments_character
    ON user_character_fragments (character_id, fragments DESC);

CREATE TABLE IF NOT EXISTS gacha_roll_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    character_id BIGINT,
    rarity_slug TEXT REFERENCES gacha_rarities(slug) ON UPDATE CASCADE,
    banner_key TEXT NOT NULL DEFAULT 'standard',
    pity_before INTEGER NOT NULL DEFAULT 0,
    pity_after INTEGER NOT NULL DEFAULT 0,
    was_pity BOOLEAN NOT NULL DEFAULT FALSE,
    was_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    fragments_awarded INTEGER NOT NULL DEFAULT 0,
    cost_currency TEXT,
    cost_amount BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gacha_roll_history_user
    ON gacha_roll_history (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gacha_roll_history_character
    ON gacha_roll_history (character_id, created_at DESC);
