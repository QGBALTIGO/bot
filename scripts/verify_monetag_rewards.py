"""Monetag rewarded-ad regression using disposable PostgreSQL only."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
url = os.environ.get("SOURCE_AUDIT_DATABASE_URL", "")
parsed = urlparse(url)
if parsed.hostname not in {"localhost", "127.0.0.1", "postgres"} or parsed.path != "/source_audit":
    raise SystemExit("Refusing any database except disposable localhost/source_audit")

os.environ.update(
    DATABASE_URL=url,
    BOT_TOKEN="999999999:synthetic-monetag-audit-only",
    BOT_USERNAME="SourceMonetagAuditBot",
    BASE_URL="https://source.invalid",
    WEBAPP_URL="https://source.invalid/menu",
    SOURCE_MINIAPP_URL="https://source.invalid/menu",
    MONETAG_SDK_URL="https://ads.invalid/sdk.js",
    MONETAG_ZONE_ID="123456",
    MONETAG_POSTBACK_SECRET="synthetic-postback-secret-never-production-123",
)

import database as db
from database_core import run
from source_features.schema import migrate
import source_monetization as ads


def one(sql, params=()):
    return run(sql, params, fetch="one")


def expect_http(status, fn):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status, (exc.status_code, status, exc.detail)
        return exc
    raise AssertionError("Expected HTTP %s" % status)


def make_user(balance=4):
    uid = 998_100_000_000 + (uuid4().int % 800_000_000)
    db.create_or_get_user(uid)
    run(
        "UPDATE users SET username=%s,full_name=%s,dado_balance=%s WHERE user_id=%s",
        ("monetag_fixture", "Monetag Fixture", int(balance), uid),
    )
    return uid


def valued(session, uid):
    return ads.process_postback(
        secret=os.environ["MONETAG_POSTBACK_SECRET"],
        ymid=session["id"],
        event_type="impression",
        reward_event_type="valued",
        zone_id=os.environ["MONETAG_ZONE_ID"],
        sub_zone_id="654321",
        request_var=ads.PLACEMENT,
        estimated_price="0.0042",
        telegram_id=str(uid),
    )


def main():
    db.create_tables()
    migrate()
    rows = []

    def check(name, fn):
        try:
            fn()
            rows.append({"case": name, "passed": True})
        except Exception as exc:
            rows.append({"case": name, "passed": False, "error": type(exc).__name__, "detail": str(exc)})
            raise

    def migration_and_config():
        migrate()
        assert one("SELECT COUNT(*) n FROM source_feature_migrations WHERE version='004_monetag_rewarded_ads'")["n"] == 1
        assert one("SELECT to_regclass('public.source_rewarded_ad_sessions') t")["t"] == "source_rewarded_ad_sessions"
        assert ads.monetag_enabled() is True
    check("migration_and_config", migration_and_config)

    uid = make_user()
    holder = {}

    def start_is_idempotent_while_pending():
        first = ads.start_rewarded_session(uid)
        second = ads.start_rewarded_session(uid)
        assert first["id"] == second["id"]
        assert second["reused"] is True
        assert first["sdkUrl"] == "https://ads.invalid/sdk.js"
        assert first["zoneId"] == "123456"
        assert first["requestVar"] == ads.PLACEMENT
        holder["session"] = first
    check("start_is_idempotent_while_pending", start_is_idempotent_while_pending)

    def postback_guards():
        session = holder["session"]
        expect_http(
            403,
            lambda: ads.process_postback(
                secret="wrong-secret-value-long-enough",
                ymid=session["id"],
                event_type="impression",
                reward_event_type="valued",
                zone_id="123456",
                sub_zone_id="1",
                request_var=ads.PLACEMENT,
                estimated_price="0.01",
                telegram_id=str(uid),
            ),
        )
        expect_http(
            400,
            lambda: ads.process_postback(
                secret=os.environ["MONETAG_POSTBACK_SECRET"],
                ymid=session["id"],
                event_type="impression",
                reward_event_type="valued",
                zone_id="999999",
                sub_zone_id="1",
                request_var=ads.PLACEMENT,
                estimated_price="0.01",
                telegram_id=str(uid),
            ),
        )
        expect_http(
            403,
            lambda: ads.process_postback(
                secret=os.environ["MONETAG_POSTBACK_SECRET"],
                ymid=session["id"],
                event_type="impression",
                reward_event_type="valued",
                zone_id="123456",
                sub_zone_id="1",
                request_var=ads.PLACEMENT,
                estimated_price="0.01",
                telegram_id=str(uid + 1),
            ),
        )
    check("postback_guards", postback_guards)

    def click_does_not_reward():
        session = holder["session"]
        before = one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"]
        result = ads.process_postback(
            secret=os.environ["MONETAG_POSTBACK_SECRET"],
            ymid=session["id"],
            event_type="click",
            reward_event_type="valued",
            zone_id="123456",
            sub_zone_id="654321",
            request_var=ads.PLACEMENT,
            estimated_price="0.003",
            telegram_id=str(uid),
        )
        after = one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"]
        assert result["rewarded"] is False
        assert int(before) == int(after)
    check("click_does_not_reward", click_does_not_reward)

    def valued_impression_rewards_once():
        session = holder["session"]
        before = int(one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"])
        first = valued(session, uid)
        second = valued(session, uid)
        after = int(one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"])
        assert first["rewarded"] is True and first["rewardedDados"] == 1
        assert second["duplicate"] is True
        assert after - before == 1
        row = ads.session_status(uid, UUID(session["id"]))
        assert row["status"] == "rewarded"
        assert row["rewardedDados"] == 1
    check("valued_impression_rewards_once", valued_impression_rewards_once)

    def cooldown_is_enforced():
        status = ads.rewarded_status(uid)
        assert status["rewardedToday"] == 1
        assert status["canStart"] is False
        expect_http(429, lambda: ads.start_rewarded_session(uid))
        ads.COOLDOWN_MINUTES = 0
    check("cooldown_is_enforced", cooldown_is_enforced)

    def non_valued_never_rewards():
        session = ads.start_rewarded_session(uid)
        before = int(one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"])
        result = ads.process_postback(
            secret=os.environ["MONETAG_POSTBACK_SECRET"],
            ymid=session["id"],
            event_type="impression",
            reward_event_type="non_valued",
            zone_id="123456",
            sub_zone_id="654321",
            request_var=ads.PLACEMENT,
            estimated_price="0",
            telegram_id=str(uid),
        )
        after = int(one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"])
        assert result["rewarded"] is False
        assert after == before
        assert one("SELECT status FROM source_rewarded_ad_sessions WHERE id=%s", (session["id"],))["status"] == "non_valued"
    check("non_valued_never_rewards", non_valued_never_rewards)

    def daily_limit_three():
        for _ in range(2):
            session = ads.start_rewarded_session(uid)
            valued(session, uid)
        status = ads.rewarded_status(uid)
        assert status["rewardedToday"] == 3
        assert status["remainingToday"] == 0
        expect_http(429, lambda: ads.start_rewarded_session(uid))
    check("daily_limit_three", daily_limit_three)

    def full_balance_blocks_wasted_ad():
        full_uid = make_user(balance=24)
        status = ads.rewarded_status(full_uid)
        assert status["dadoBalance"] == 24
        assert status["canStart"] is False
        expect_http(409, lambda: ads.start_rewarded_session(full_uid))
    check("full_balance_blocks_wasted_ad", full_balance_blocks_wasted_ad)

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "monetag-rewards.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": all(row["passed"] for row in rows), "cases": rows}, ensure_ascii=False, indent=2))
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
