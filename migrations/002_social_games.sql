-- Source social games: additive configuration only.
CREATE TABLE IF NOT EXISTS source_capture_group_settings (
    chat_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    message_threshold INTEGER NOT NULL DEFAULT 75
        CHECK(message_threshold BETWEEN 20 AND 500),
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS source_capture_group_settings_updated
ON source_capture_group_settings(updated_at DESC);
