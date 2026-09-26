"""Source <-> AniNexus account-link integration tests on a disposable PostgreSQL database."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlparse
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
    BOT_TOKEN="999999999:synthetic-aninexus-bridge-only",
    BOT_USERNAME="SourceAuditFixtureBot",
    BASE_URL="https://source.invalid",
    WEBAPP_URL="https://source.invalid/menu",
    SOURCE_MINIAPP_URL="https://source.invalid/menu",
    ANINEXUS_PUBLIC_ORIGIN="https://aninexus.invalid",
)

import database as db
from database_core import run
from cards_service import build_cards_final_data
from source_features.schema import migrate
from source_integrations import aninexus


def one(sql, params=()):
    return run(sql, params, fetch="one")


def expect_http(status, fn):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == status, (exc.status_code, status, exc.detail)
        return exc
    raise AssertionError(f"Expected HTTP {status}")


def token_from(result):
    parsed_url = urlparse(result["url"])
    assert parsed_url.scheme == "https" and parsed_url.netloc == "aninexus.invalid"
    assert parsed_url.query == ""
    values = parse_qs(parsed_url.fragment)
    token = values.get("source_token", [""])[0]
    assert len(token) >= 32
    return token


def make_user():
    uid = 997_300_000_000 + (uuid4().int % 900_000_000)
    db.create_or_get_user(uid)
    run("UPDATE users SET username=%s,full_name=%s,coins=%s WHERE user_id=%s", ("source_fixture", "Source Fixture", 321, uid))
    cards = sorted(build_cards_final_data()["characters_by_id"])
    cid = int(cards[0])
    run(
        "INSERT INTO user_card_collection(user_id,character_id,quantity) VALUES(%s,%s,3) ON CONFLICT(user_id,character_id) DO UPDATE SET quantity=3",
        (uid, cid),
    )
    return uid, cid


def main():
    db.create_tables()
    migrate()
    uid, cid = make_user()
    rows = []

    def check(name, fn):
        try:
            fn()
            rows.append({"case": name, "passed": True})
        except Exception as exc:
            rows.append({"case": name, "passed": False, "error": type(exc).__name__, "detail": str(exc)})
            raise

    def migration_is_repeatable():
        migrate(); migrate()
        assert one("SELECT COUNT(*) n FROM source_feature_migrations WHERE version IN ('001_collecting','002_aninexus_link','003_aninexus_rewards')")["n"] == 3
        assert one("SELECT to_regclass('public.source_aninexus_links') linked")["linked"] == "source_aninexus_links"
    check("migration_is_repeatable", migration_is_repeatable)

    first = aninexus.create_link_token(uid)
    first_token = token_from(first)

    def plaintext_token_never_persisted():
        expected_hash = hashlib.sha256(first_token.encode()).hexdigest()
        stored = one("SELECT token_hash,consumed_at FROM source_aninexus_link_tokens WHERE user_id=%s AND token_hash=%s", (uid, expected_hash))
        assert stored["token_hash"] == expected_hash
        assert stored["token_hash"] != first_token
        assert stored["consumed_at"] is None
    check("plaintext_token_never_persisted", plaintext_token_never_persisted)

    def token_is_single_use_under_concurrency():
        def consume(_):
            try:
                return ("ok", aninexus.consume_link_token(first_token))
            except HTTPException as exc:
                return ("error", exc.status_code)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(consume, range(2)))
        assert sum(1 for kind, _ in outcomes if kind == "ok") == 1, outcomes
        assert sum(1 for kind, value in outcomes if kind == "error" and value == 410) == 1, outcomes
        result = next(value for kind, value in outcomes if kind == "ok")
        link_id = UUID(result["linkId"])
        assert result["sourceSubject"].startswith("src_") and len(result["sourceSubject"]) == 68
        assert str(uid) not in result["sourceSubject"]
        holder["subject"] = result["sourceSubject"]
        assert result["profile"]["stats"]["coins"] == 371
        assert result["reward"]["newlyGranted"] is True
        assert result["reward"]["coinsGranted"] == 50
        assert result["reward"]["dadosGranted"] == 1
        status = aninexus.link_status(uid)
        assert status["reward"]["claimed"] is True
        assert status["reward"]["available"] is False
        assert one("SELECT coins FROM users WHERE user_id=%s", (uid,))["coins"] == 371
        assert one("SELECT dado_balance FROM users WHERE user_id=%s", (uid,))["dado_balance"] == 5
        assert one("SELECT COUNT(*) n FROM shop_transactions WHERE user_id=%s AND type='aninexus_link_reward'", (uid,))["n"] == 1
        notice = one("SELECT kind,status,caption FROM telegram_outbox WHERE dedupe_key=%s", (f"aninexus-link-reward:{uid}",))
        assert notice["kind"] == "text"
        assert notice["status"] == "pending"
        assert "Source AniNexus conectado" in notice["caption"]
        assert "+50 Coins" in notice["caption"]
        assert result["profile"]["stats"]["uniqueCharacters"] >= 1
        assert "user_id" not in json.dumps(result["profile"]).lower()
        assert aninexus.snapshot_for_link(link_id)["username"] == "source_fixture"
        return link_id
    holder = {}
    def single_use_case(): holder["old"] = token_is_single_use_under_concurrency()
    check("token_is_single_use_under_concurrency", single_use_case)

    def expired_token_is_rejected():
        result = aninexus.create_link_token(uid)
        token = token_from(result)
        run("UPDATE source_aninexus_link_tokens SET expires_at=NOW()-INTERVAL '1 second' WHERE token_hash=%s", (hashlib.sha256(token.encode()).hexdigest(),))
        expect_http(410, lambda: aninexus.consume_link_token(token))
    check("expired_token_is_rejected", expired_token_is_rejected)

    def relink_rotates_opaque_id_and_invalidates_old_link():
        # Expired-token creation above intentionally removed any pending token, not the active link.
        token = token_from(aninexus.create_link_token(uid))
        result = aninexus.consume_link_token(token)
        new_id = UUID(result["linkId"])
        assert new_id != holder["old"]
        assert result["sourceSubject"] == holder["subject"]
        expect_http(404, lambda: aninexus.snapshot_for_link(holder["old"]))
        assert aninexus.snapshot_for_link(new_id)["stats"]["totalCharacters"] >= 3
        assert result["reward"]["newlyGranted"] is False
        assert one("SELECT coins FROM users WHERE user_id=%s", (uid,))["coins"] == 371
        assert one("SELECT COUNT(*) n FROM shop_transactions WHERE user_id=%s AND type='aninexus_link_reward'", (uid,))["n"] == 1
        assert one("SELECT COUNT(*) n FROM telegram_outbox WHERE dedupe_key=%s", (f"aninexus-link-reward:{uid}",))["n"] == 1
        holder["new"] = new_id
        holder["revoke"] = result["revokeToken"]
    check("relink_rotates_opaque_id_and_invalidates_old_link", relink_rotates_opaque_id_and_invalidates_old_link)

    def wrong_revoke_secret_does_not_unlink():
        assert aninexus.revoke_link(holder["new"], "x" * 32) is False
        assert aninexus.link_status(uid)["linked"] is True
    check("wrong_revoke_secret_does_not_unlink", wrong_revoke_secret_does_not_unlink)

    def correct_revoke_secret_unlinks():
        assert aninexus.revoke_link(holder["new"], holder["revoke"]) is True
        assert aninexus.link_status(uid)["linked"] is False
        expect_http(404, lambda: aninexus.snapshot_for_link(holder["new"]))
    check("correct_revoke_secret_unlinks", correct_revoke_secret_unlinks)

    def source_side_unlink_is_idempotent():
        token = token_from(aninexus.create_link_token(uid))
        linked = aninexus.consume_link_token(token)
        assert aninexus.link_status(uid)["linked"] is True
        assert aninexus.revoke_for_user(uid) is True
        assert aninexus.revoke_for_user(uid) is False
        expect_http(404, lambda: aninexus.snapshot_for_link(UUID(linked["linkId"])))
    check("source_side_unlink_is_idempotent", source_side_unlink_is_idempotent)

    def unlink_invalidates_unconsumed_handoff():
        pending = token_from(aninexus.create_link_token(uid))
        assert aninexus.revoke_for_user(uid) is True
        expect_http(410, lambda: aninexus.consume_link_token(pending))
    check("unlink_invalidates_unconsumed_handoff", unlink_invalidates_unconsumed_handoff)

    def remote_disconnect_invalidates_pending_reconnect():
        first_token = token_from(aninexus.create_link_token(uid))
        linked = aninexus.consume_link_token(first_token)
        pending = token_from(aninexus.create_link_token(uid))
        assert aninexus.revoke_link(UUID(linked["linkId"]), linked["revokeToken"]) is True
        expect_http(410, lambda: aninexus.consume_link_token(pending))
    check("remote_disconnect_invalidates_pending_reconnect", remote_disconnect_invalidates_pending_reconnect)

    def existing_link_can_claim_reward_once():
        legacy_uid, _ = make_user()
        link_id = uuid4()
        revoke_token = "legacy-revoke-token-" + uuid4().hex
        run(
            """
            INSERT INTO source_aninexus_links(user_id,link_id,revoke_hash,linked_at,updated_at,revoked_at)
            VALUES(%s,%s,%s,NOW(),NOW(),NULL)
            ON CONFLICT(user_id) DO UPDATE SET
              link_id=EXCLUDED.link_id,revoke_hash=EXCLUDED.revoke_hash,
              linked_at=NOW(),updated_at=NOW(),revoked_at=NULL,
              reward_claimed_at=NULL,reward_coins=0,reward_dados=0
            """,
            (legacy_uid, link_id, hashlib.sha256(revoke_token.encode()).hexdigest()),
        )
        before = one("SELECT coins,dado_balance FROM users WHERE user_id=%s", (legacy_uid,))
        first = aninexus.claim_link_reward(legacy_uid)
        second = aninexus.claim_link_reward(legacy_uid)
        after = one("SELECT coins,dado_balance FROM users WHERE user_id=%s", (legacy_uid,))
        assert first["newlyGranted"] is True
        assert second["newlyGranted"] is False
        assert int(after["coins"]) - int(before["coins"]) == 50
        assert int(after["dado_balance"]) - int(before["dado_balance"]) == 1
        assert one("SELECT COUNT(*) n FROM shop_transactions WHERE user_id=%s AND type='aninexus_link_reward'", (legacy_uid,))["n"] == 1
    check("existing_link_can_claim_reward_once", existing_link_can_claim_reward_once)

    def full_dado_balance_never_overflows_cap():
        full_uid, _ = make_user()
        run("UPDATE users SET dado_balance=24 WHERE user_id=%s", (full_uid,))
        token = token_from(aninexus.create_link_token(full_uid))
        linked = aninexus.consume_link_token(token)
        assert linked["reward"]["coinsGranted"] == 50
        assert linked["reward"]["dadosGranted"] == 0
        balances = one("SELECT coins,dado_balance FROM users WHERE user_id=%s", (full_uid,))
        assert int(balances["coins"]) == 371
        assert int(balances["dado_balance"]) == 24
    check("full_dado_balance_never_overflows_cap", full_dado_balance_never_overflows_cap)

    def reward_cannot_be_farmed_by_recreating_source_account():
        farm_uid, _ = make_user()
        first_token = token_from(aninexus.create_link_token(farm_uid))
        first = aninexus.consume_link_token(first_token)
        subject = first["sourceSubject"]
        assert first["reward"]["newlyGranted"] is True
        assert one("SELECT COUNT(*) n FROM source_aninexus_reward_claims WHERE source_subject=%s", (subject,))["n"] == 1

        # Simulate account recreation while intentionally preserving the opaque
        # anti-abuse marker. No Telegram id is stored in that durable ledger.
        run("DELETE FROM source_aninexus_link_tokens WHERE user_id=%s", (farm_uid,))
        run("DELETE FROM source_aninexus_links WHERE user_id=%s", (farm_uid,))
        run("DELETE FROM user_progress WHERE user_id=%s", (farm_uid,))
        run("DELETE FROM user_card_collection WHERE user_id=%s", (farm_uid,))
        run("DELETE FROM users WHERE user_id=%s", (farm_uid,))
        db.create_or_get_user(farm_uid)
        run("UPDATE users SET coins=0,dado_balance=4 WHERE user_id=%s", (farm_uid,))

        second_token = token_from(aninexus.create_link_token(farm_uid))
        second = aninexus.consume_link_token(second_token)
        balances = one("SELECT coins,dado_balance FROM users WHERE user_id=%s", (farm_uid,))
        assert second["sourceSubject"] == subject
        assert second["reward"]["newlyGranted"] is False
        assert second["reward"]["claimed"] is True
        assert int(balances["coins"]) == 0
        assert int(balances["dado_balance"]) == 4
        assert one("SELECT COUNT(*) n FROM source_aninexus_reward_claims WHERE source_subject=%s", (subject,))["n"] == 1
    check("reward_cannot_be_farmed_by_recreating_source_account", reward_cannot_be_farmed_by_recreating_source_account)

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "aninexus-bridge.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": all(row["passed"] for row in rows), "cases": rows}, ensure_ascii=False, indent=2))
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
