-- AniNexus integration benefits. Additive and idempotent.
ALTER TABLE source_aninexus_links
  ADD COLUMN IF NOT EXISTS reward_claimed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS reward_coins INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reward_dados INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS source_aninexus_links_reward
  ON source_aninexus_links(user_id, reward_claimed_at);

CREATE TABLE IF NOT EXISTS source_aninexus_reward_claims (
  source_subject TEXT PRIMARY KEY CHECK (source_subject ~ '^src_[a-f0-9]{64}$'),
  reward_coins INTEGER NOT NULL DEFAULT 0,
  reward_dados INTEGER NOT NULL DEFAULT 0,
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
