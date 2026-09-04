CREATE TABLE IF NOT EXISTS source_v2_wallet (
    user_id BIGINT PRIMARY KEY,
    prisms BIGINT NOT NULL DEFAULT 0 CHECK (prisms >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_v2_shop_stock (
    rotation_date DATE NOT NULL,
    character_id BIGINT NOT NULL,
    price_prisms BIGINT NOT NULL CHECK (price_prisms > 0),
    stock_limit INTEGER NOT NULL DEFAULT 10 CHECK (stock_limit > 0),
    sold_count INTEGER NOT NULL DEFAULT 0 CHECK (sold_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rotation_date, character_id),
    CHECK (sold_count <= stock_limit)
);

CREATE INDEX IF NOT EXISTS idx_source_v2_shop_stock_date
    ON source_v2_shop_stock (rotation_date, sold_count, character_id);
