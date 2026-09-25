-- Additive migration. Run once under the Source migration lock; never rewrites balances.
CREATE TABLE IF NOT EXISTS source_collecting_settings (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    discoverable BOOLEAN NOT NULL DEFAULT FALSE,
    share_inline BOOLEAN NOT NULL DEFAULT FALSE,
    preserve_last BOOLEAN NOT NULL DEFAULT TRUE,
    equipped_cosmetic TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS source_card_protection (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL CHECK(character_id > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(user_id, character_id)
);
CREATE TABLE IF NOT EXISTS source_wishlist (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL CHECK(character_id > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(user_id, character_id)
);
CREATE INDEX IF NOT EXISTS source_wishlist_character ON source_wishlist(character_id, user_id);
CREATE TABLE IF NOT EXISTS source_operations (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    operation TEXT NOT NULL,
    digest TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(user_id, request_id)
);
CREATE INDEX IF NOT EXISTS source_operations_created ON source_operations(created_at);
CREATE TABLE IF NOT EXISTS source_reservations (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    character_id BIGINT NOT NULL,
    owner_type TEXT NOT NULL CHECK(owner_type IN ('market')),
    owner_id UUID NOT NULL,
    -- Listings with bids remain reserved until settled, even after their closing time.
    PRIMARY KEY(user_id, character_id)
);
CREATE TABLE IF NOT EXISTS source_workshop_wallet (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    fragments INTEGER NOT NULL DEFAULT 0 CHECK(fragments >= 0)
);
CREATE TABLE IF NOT EXISTS source_cosmetics (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    cosmetic_id TEXT NOT NULL,
    label TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('frame','title','badge')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(user_id, cosmetic_id)
);
CREATE TABLE IF NOT EXISTS source_market (
    id UUID PRIMARY KEY,
    seller_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    character_id BIGINT NOT NULL CHECK(character_id > 0),
    quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 20),
    kind TEXT NOT NULL CHECK(kind IN ('fixed', 'auction')),
    price INTEGER NOT NULL CHECK(price BETWEEN 1 AND 100000),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','sold','cancelled','expired')),
    bidder_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    bid INTEGER NOT NULL DEFAULT 0 CHECK(bid >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ends_at TIMESTAMPTZ NOT NULL,
    hard_ends_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CHECK(bidder_id IS NULL OR bidder_id <> seller_id)
);
CREATE INDEX IF NOT EXISTS source_market_active ON source_market(status, ends_at);
CREATE INDEX IF NOT EXISTS source_market_seller ON source_market(seller_id, created_at DESC);
CREATE TABLE IF NOT EXISTS source_events (
    id UUID PRIMARY KEY,
    title VARCHAR(80) NOT NULL,
    description VARCHAR(1000) NOT NULL,
    character_ids BIGINT[] NOT NULL,
    goal INTEGER NOT NULL CHECK(goal BETWEEN 1 AND 100000),
    daily_limit INTEGER NOT NULL CHECK(daily_limit BETWEEN 1 AND 5),
    reward_label VARCHAR(60) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','cancelled')),
    created_by BIGINT NOT NULL,
    published_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK(ends_at > starts_at)
);
CREATE TABLE IF NOT EXISTS source_contributions (
    event_id UUID NOT NULL REFERENCES source_events(id),
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    day DATE NOT NULL,
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 5),
    character_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(event_id,user_id,day,slot),
    UNIQUE(event_id,user_id,day,character_id)
);
ALTER TABLE card_trades ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE card_trades ADD COLUMN IF NOT EXISTS from_confirmed INTEGER DEFAULT 1;
ALTER TABLE card_trades ADD COLUMN IF NOT EXISTS to_confirmed INTEGER;
ALTER TABLE card_trades ADD COLUMN IF NOT EXISTS changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Defense in depth: old routes cannot remove a manually protected or market-reserved card.
-- Favorite is also protected. The account-deletion path explicitly clears these preferences first.
CREATE OR REPLACE FUNCTION source_guard_collection() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.quantity >= OLD.quantity THEN RETURN NEW; END IF;
    IF EXISTS(SELECT 1 FROM source_card_protection WHERE user_id=OLD.user_id AND character_id=OLD.character_id)
       OR EXISTS(SELECT 1 FROM user_profile_settings WHERE user_id=OLD.user_id AND favorite_character_id=OLD.character_id)
    THEN RAISE EXCEPTION 'source_card_protected' USING ERRCODE='P0001'; END IF;
    IF EXISTS(SELECT 1 FROM source_reservations WHERE user_id=OLD.user_id AND character_id=OLD.character_id)
    THEN RAISE EXCEPTION 'source_card_reserved' USING ERRCODE='P0001'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS source_collection_guard ON user_card_collection;
CREATE TRIGGER source_collection_guard BEFORE DELETE OR UPDATE OF quantity ON user_card_collection
    FOR EACH ROW EXECUTE FUNCTION source_guard_collection();
