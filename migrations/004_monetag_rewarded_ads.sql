-- Rewarded ads (Monetag) for Source MiniApp.
CREATE TABLE IF NOT EXISTS source_rewarded_ad_sessions (
  id UUID PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  provider TEXT NOT NULL DEFAULT 'monetag',
  placement TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  reward_type TEXT NOT NULL DEFAULT 'dado',
  reward_amount INTEGER NOT NULL DEFAULT 1,
  reward_dados INTEGER NOT NULL DEFAULT 0,
  rewarded_dados INTEGER NOT NULL DEFAULT 0,
  reward_coins INTEGER NOT NULL DEFAULT 0,
  rewarded_coins INTEGER NOT NULL DEFAULT 0,
  zone_id TEXT,
  sub_zone_id TEXT,
  event_type TEXT,
  reward_event_type TEXT,
  estimated_price NUMERIC(14,8),
  telegram_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  confirmed_at TIMESTAMPTZ,
  rewarded_at TIMESTAMPTZ,
  CHECK (status IN ('pending','rewarded','non_valued','expired','cancelled')),
  CHECK (reward_type IN ('dado','coins')),
  CHECK (reward_amount > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS source_rewarded_ad_one_pending_per_user
  ON source_rewarded_ad_sessions(user_id)
  WHERE status='pending';
CREATE INDEX IF NOT EXISTS source_rewarded_ad_user_created
  ON source_rewarded_ad_sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS source_rewarded_ad_rewarded_at
  ON source_rewarded_ad_sessions(user_id, rewarded_at DESC)
  WHERE status='rewarded';
