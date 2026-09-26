-- Source <-> AniNexus account linking. Additive and safe to rerun through source_features.schema.
CREATE TABLE IF NOT EXISTS source_aninexus_link_tokens (
    token_hash TEXT PRIMARY KEY CHECK (char_length(token_hash) = 64),
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS source_aninexus_link_tokens_user
    ON source_aninexus_link_tokens(user_id, expires_at DESC);

CREATE TABLE IF NOT EXISTS source_aninexus_links (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    link_id UUID NOT NULL UNIQUE,
    revoke_hash TEXT NOT NULL CHECK (char_length(revoke_hash) = 64),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS source_aninexus_links_active
    ON source_aninexus_links(link_id) WHERE revoked_at IS NULL;
