"""Real PostgreSQL integration/race tests. Hard refusal of production databases."""

from __future__ import annotations
import asyncio
import itertools
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
url = os.environ.get("SOURCE_AUDIT_DATABASE_URL", "")
parsed = urlparse(url)
if (
    parsed.hostname not in {"localhost", "127.0.0.1", "postgres"}
    or parsed.path != "/source_audit"
):
    raise SystemExit("Refusing any database except disposable localhost/source_audit")
os.environ.update(
    DATABASE_URL=url,
    BOT_TOKEN="999999999:synthetic-collecting-test-only",
    BOT_USERNAME="SourceAuditFixtureBot",
    BASE_URL="https://source.invalid",
    WEBAPP_URL="https://source.invalid/menu",
    SOURCE_MINIAPP_URL="https://source.invalid/menu",
)
from database_core import run, pool
import database as db
import database_aninexus_social as social
import database_profile as profile
from source_features import collection, market, activity, events, common
from source_features.errors import FeatureError
from source_features.schema import migrate
from cards_service import build_cards_final_data

db.create_tables()
C1, C2, C3, C4 = sorted(build_cards_final_data()["characters_by_id"])[:4]
seq = itertools.count(996200001)
results = []


def user(coins=100, cards=None):
    uid = next(seq)
    db.create_or_get_user(uid)
    run(
        "UPDATE users SET coins=%s,dado_balance=5,dado_slot=%s WHERE user_id=%s",
        (coins, db._slot_number_from_dt(db._now_sp()), uid),
    )
    if cards:
        for cid, amount in cards.items():
            run(
                "INSERT INTO user_card_collection(user_id,character_id,quantity) VALUES(%s,%s,%s)",
                (uid, cid, amount),
            )
    return uid


def scalar(sql, params=()):
    return next(iter(run(sql, params, fetch="one").values()))


def coins(uid):
    return scalar("SELECT coins FROM users WHERE user_id=%s", (uid,))


def qty(uid, cid):
    return db.get_user_card_quantity(uid, cid)


def key():
    return str(uuid4())


def denied(fn, code=None):
    try:
        fn()
    except FeatureError as exc:
        if code:
            assert exc.code == code, (exc.code, code)
        return
    raise AssertionError("Expected rejection")


def race(fn, n=6):
    barrier = Barrier(n)

    def call(i):
        barrier.wait(timeout=10)
        try:
            return fn(i)
        except FeatureError as exc:
            return {"ok": False, "error": exc.code}

    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(call, range(n), timeout=40))


def check(fn):
    started = time.perf_counter()
    try:
        fn()
        row = {"case": fn.__name__, "passed": True}
    except Exception as exc:
        row = {
            "case": fn.__name__,
            "passed": False,
            "error": type(exc).__name__,
            "detail": str(exc),
            "trace": traceback.format_exc(),
        }
    row["ms"] = round((time.perf_counter() - started) * 1000, 2)
    results.append(row)
    print(fn.__name__, row["passed"], flush=True)


def listing(uid, cid=C1, kind="fixed", quantity=1, price=10, request_id=None):
    return market.create(
        uid,
        dict(
            character_id=cid,
            kind=kind,
            quantity=quantity,
            price=price,
            hours=1,
            request_id=request_id or key(),
        ),
    )["id"]


def record(mid):
    return run("SELECT * FROM source_market WHERE id=%s", (mid,), fetch="one")


def spec():
    now = datetime.now(timezone.utc)
    return dict(
        title="Expedição de teste",
        description="Manifesto sintético com dados do catálogo",
        character_ids=[C1, C2],
        goal=2,
        daily_limit=1,
        reward_label="Explorador de teste",
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
        request_id=key(),
    )


@check
def migration_is_additive_and_repeatable():
    uid = user(73, {C1: 2})
    migrate()
    migrate()
    assert coins(uid) == 73 and qty(uid, C1) == 2
    assert (
        scalar(
            "SELECT COUNT(*) FROM source_feature_migrations WHERE version='001_collecting'"
        )
        == 1
    )


@check
def protection_prevents_legacy_sale_and_direct_deletion():
    uid = user(cards={C1: 2})
    collection.set_protection(uid, C1, True)
    assert db.sell_character(uid, C1)["error"] == "card_protected"
    try:
        run(
            "DELETE FROM user_card_collection WHERE user_id=%s AND character_id=%s",
            (uid, C1),
        )
    except Exception as exc:
        assert "source_card_protected" in str(exc)
    else:
        raise AssertionError("SQL guard did not protect the card")
    assert qty(uid, C1) == 2 and coins(uid) == 100
    collection.set_protection(uid, C1, False)
    assert db.sell_character(uid, C1)["ok"]


@check
def another_user_cannot_protect_or_unlock_someone_elses_card():
    a, b = user(cards={C1: 2}), user()
    denied(lambda: collection.set_protection(b, C1, True), "card_missing")
    collection.set_protection(a, C1, True)
    collection.set_protection(b, C1, False)
    assert collection.cards(a, view="protected")["items"][0]["id"] == C1


@check
def favorite_is_protected_across_market_and_workshop():
    a = user(cards={C1: 3})
    profile.set_profile_favorite(a, C1)
    denied(lambda: listing(a), "card_protected")
    denied(
        lambda: collection.workshop_recycle(
            a, [{"character_id": C1, "quantity": 1}], key()
        ),
        "card_protected",
    )
    assert not db.sell_character(a, C1)["ok"]


@check
def reservation_cannot_be_protected_or_favorited_or_sold():
    a = user(cards={C1: 3})
    mid = listing(a)
    denied(lambda: collection.set_protection(a, C1, True), "card_reserved")
    denied(lambda: profile.set_profile_favorite(a, C1), "card_reserved")
    assert db.sell_character(a, C1)["error"] == "card_reserved"
    assert not social.create_trade_offer(a, user(cards={C2: 1}), C1, C2)["ok"]
    assert record(mid)["status"] == "active"


@check
def wishlist_is_idempotent_and_work_excludes_owned():
    a = user(cards={C1: 1})
    assert collection.wishes(a, [C1, C2])["added"] == 2
    assert collection.wishes(a, [C1, C2])["added"] == 0
    collection.wishes(a, [C1, C2], False)
    collection.wishes(a, [C1, C2], missing_only=True)
    assert [r["id"] for r in collection.cards(a, view="wishes")["items"]] == [C2]
    assert collection.cards(a, q=str(C2), view="catalog")["items"][0]["id"] == C2


@check
def matches_require_both_opt_ins_and_respect_private_profiles():
    a = user(cards={C1: 2})
    b = user(cards={C2: 2})
    collection.wishes(a, [C2])
    collection.wishes(b, [C1])
    assert collection.matches(a)["opt_in_required"]
    collection.save_settings(a, {"discoverable": True})
    assert not collection.matches(a)["items"]
    collection.save_settings(b, {"discoverable": True})
    matches = collection.matches(a)["items"]
    assert any(r["user_id"] == b for r in matches)
    collection.set_protection(b, C2, True)
    assert not any(r["user_id"] == b for r in collection.matches(a)["items"])
    collection.set_protection(b, C2, False)
    run(
        "INSERT INTO user_profile_settings(user_id,private_profile) VALUES(%s,TRUE) ON CONFLICT(user_id) DO UPDATE SET private_profile=TRUE",
        (b,),
    )
    assert not any(r["user_id"] == b for r in collection.matches(a)["items"])


@check
def workshop_preserves_last_copy_and_atomic_selection():
    a = user(cards={C1: 3, C2: 1})
    denied(
        lambda: collection.workshop_recycle(
            a,
            [{"character_id": C1, "quantity": 1}, {"character_id": C2, "quantity": 1}],
            key(),
        ),
        "last_copy",
    )
    assert qty(a, C1) == 3 and collection.workshop_state(a)["fragments"] == 0


@check
def workshop_replays_lost_response_without_consuming_again():
    a = user(cards={C1: 3})
    rid = key()
    payload = [{"character_id": C1, "quantity": 1}]
    first = collection.workshop_recycle(a, payload, rid)
    assert collection.workshop_recycle(a, payload, rid) == first
    assert qty(a, C1) == 2 and collection.workshop_state(a)["fragments"] == 1
    denied(
        lambda: collection.workshop_recycle(
            a, [{"character_id": C1, "quantity": 2}], rid
        ),
        "request_conflict",
    )


@check
def workshop_concurrent_requests_do_not_consume_last_copy():
    a = user(cards={C1: 3})
    r = race(
        lambda _: collection.workshop_recycle(
            a, [{"character_id": C1, "quantity": 1}], key()
        )
    )
    assert sum(bool(x.get("ok")) for x in r) == 2
    assert qty(a, C1) == 1 and collection.workshop_state(a)["fragments"] == 2


@check
def cosmetic_crafting_is_atomic_owned_and_equip_scoped():
    a = user(cards={C1: 12})
    b = user()
    collection.workshop_recycle(a, [{"character_id": C1, "quantity": 10}], key())
    with patch.object(
        collection, "cosmetic", side_effect=RuntimeError("injected write failure")
    ):
        try:
            collection.craft(a, "frame-bronze", key())
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected rollback")
    assert collection.workshop_state(a)["fragments"] == 10
    rid = key()
    first = collection.craft(a, "frame-bronze", rid)
    assert collection.craft(a, "frame-bronze", rid) == first
    assert collection.workshop_state(a)["fragments"] == 0
    denied(lambda: collection.craft(a, "frame-bronze", key()), "already_owned")
    denied(lambda: collection.equip(b, "frame-bronze"), "cosmetic_missing")
    collection.equip(a, "frame-bronze")
    assert collection.settings(a)["equipped_cosmetic"] == "frame-bronze"


@check
def fixed_sale_race_has_one_winner_and_conserves_coins():
    a = user(cards={C1: 3})
    buyers = [user() for _ in range(6)]
    mid = listing(a)
    r = race(lambda i: market.act(buyers[i], mid, "buy", key(), 1))
    assert sum(bool(x.get("ok")) for x in r) == 1
    assert qty(a, C1) == 2 and sum(qty(b, C1) for b in buyers) == 1
    assert coins(a) + sum(coins(b) for b in buyers) == 700
    assert record(mid)["status"] == "sold"


@check
def market_purchase_replay_and_balance_validation():
    a = user(cards={C1: 3})
    b = user(1)
    mid = listing(a)
    denied(lambda: market.act(b, mid, "buy", key(), 1), "no_coins")
    assert qty(a, C1) == 3 and record(mid)["status"] == "active"
    run("UPDATE users SET coins=100 WHERE user_id=%s", (b,))
    rid = key()
    result = market.act(b, mid, "buy", rid, 1)
    assert market.act(b, mid, "buy", rid, 1) == result and coins(b) == 90


@check
def market_failure_rolls_back_funds_inventory_and_reservation():
    a = user(cards={C1: 3})
    b = user()
    mid = listing(a)
    with patch.object(
        common, "_ledger", side_effect=RuntimeError("injected ledger failure")
    ):
        try:
            market.act(b, mid, "buy", key(), 1)
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected rollback")
    assert coins(a) == coins(b) == 100 and qty(a, C1) == 3 and qty(b, C1) == 0
    assert (
        scalar("SELECT COUNT(*) FROM source_reservations WHERE owner_id=%s", (mid,))
        == 1
    )


@check
def cancellation_requires_owner_and_releases_inventory():
    a = user(cards={C1: 3})
    b = user()
    mid = listing(a)
    denied(lambda: market.act(b, mid, "cancel", key(), 1), "forbidden")
    market.act(a, mid, "cancel", key(), 1)
    assert not scalar(
        "SELECT COUNT(*) FROM source_reservations WHERE owner_id=%s", (mid,)
    )
    collection.set_protection(a, C1, True)


@check
def auction_escrow_refunds_and_raise_only_debits_difference():
    a = user(cards={C1: 3})
    b, c = user(), user()
    mid = listing(a, kind="auction")
    market.act(b, mid, "bid", key(), 1, 10)
    assert coins(b) == 90
    market.act(b, mid, "bid", key(), 2, 15)
    assert coins(b) == 85
    market.act(c, mid, "bid", key(), 3, 20)
    assert coins(b) == 100 and coins(c) == 80
    denied(lambda: market.act(a, mid, "cancel", key(), 4), "has_bids")
    denied(lambda: market.act(b, mid, "bid", key(), 3, 25), "listing_changed")
    assert coins(a) + coins(b) + coins(c) + record(mid)["bid"] == 300


@check
def auction_settlement_is_authorized_and_one_time():
    a = user(cards={C1: 3})
    b, c = user(), user()
    mid = listing(a, kind="auction")
    market.act(b, mid, "bid", key(), 1, 10)
    denied(lambda: market.settle(mid, c), "forbidden")
    denied(lambda: market.settle(mid, b), "not_ended")
    run(
        "UPDATE source_market SET ends_at=NOW()-INTERVAL '1 second' WHERE id=%s", (mid,)
    )
    market.settle(mid, b)
    market.settle(mid, a)
    assert qty(b, C1) == 1 and qty(a, C1) == 2 and coins(a) == 110 and coins(b) == 90


@check
def anti_sniping_never_extends_past_hard_deadline():
    a = user(cards={C1: 3})
    b = user()
    mid = listing(a, kind="auction")
    run(
        "UPDATE source_market SET ends_at=NOW()+INTERVAL '10 seconds',hard_ends_at=NOW()+INTERVAL '35 seconds' WHERE id=%s",
        (mid,),
    )
    market.act(b, mid, "bid", key(), 1, 10)
    r = record(mid)
    assert r["ends_at"] == r["hard_ends_at"]


@check
def last_copy_and_active_listing_limit_are_server_enforced():
    a = user(cards={C1: 1})
    denied(lambda: listing(a), "last_copy")
    collection.save_settings(a, {"preserve_last": False})
    assert listing(a)


@check
def amended_trade_clears_both_acceptances_and_old_button_cannot_accept():
    a = user(cards={C1: 2, C3: 2})
    b = user(cards={C2: 2})
    tid = social.create_trade_offer(a, b, C1, C2)["trade_id"]
    revised = social.revise_trade_offer(a, tid, C3, 1)
    assert revised["revision"] == 2
    assert social.respond_trade_offer(b, tid, "accept")["error"] == "trade_changed"
    assert (
        social.respond_trade_offer(b, tid, "accept", expected_revision=1)["error"]
        == "trade_changed"
    )
    assert (
        social.respond_trade_offer(b, tid, "accept", expected_revision=2)["status"]
        == "pending"
    )
    assert qty(a, C3) == 2
    assert (
        social.respond_trade_offer(a, tid, "accept", expected_revision=2)["status"]
        == "completed"
    )
    assert qty(a, C3) == 1 and qty(b, C3) == 1 and qty(a, C1) == 2


@check
def trade_amendment_requires_membership_and_current_version():
    a = user(cards={C1: 2, C3: 2})
    b = user(cards={C2: 2})
    c = user(cards={C4: 2})
    tid = social.create_trade_offer(a, b, C1, C2)["trade_id"]
    denied(lambda: social.revise_trade_offer(c, tid, C4, 1), "forbidden")
    denied(lambda: social.revise_trade_offer(a, tid, C3, 99), "trade_changed")
    assert (
        social.respond_trade_offer(c, tid, "accept", expected_revision=1)["error"]
        == "forbidden"
    )
    assert social.respond_trade_offer(a, tid, "reject")["status"] == "rejected"
    denied(lambda: social.revise_trade_offer(a, tid, C3, 1), "trade_expired")


@check
def daily_commands_and_miniapp_share_single_server_day():
    a = user()
    r = race(lambda _: activity.claim(a))
    assert sum(not x["already_claimed"] for x in r) == 1
    assert activity.calendar(a)["claimed_today"]
    assert scalar("SELECT COUNT(*) FROM daily_rewards WHERE user_id=%s", (a,)) == 1


@check
def daily_giro_actually_credits_a_dado_and_full_balance_falls_back():
    a = user()
    day = db._daily_day_start_ts_sp()
    with patch.object(db.random, "random", return_value=0):
        assert db.claim_daily_reward(a, day, 1, 3, 0.15)["type"] == "giro"
    assert scalar("SELECT dado_balance FROM users WHERE user_id=%s", (a,)) == 6
    b = user()
    run("UPDATE users SET dado_balance=24 WHERE user_id=%s", (b,))
    with patch.object(db.random, "random", return_value=0):
        assert db.claim_daily_reward(b, day, 1, 3, 0.15)["type"] == "coins"
    assert coins(b) == 101


@check
def weekly_cosmetic_cannot_be_claimed_early_or_twice():
    a = user()
    denied(lambda: activity.claim_milestone(a), "milestone_unavailable")
    day = db._daily_day_start_ts_sp()
    for n in range(7):
        run(
            "INSERT INTO daily_rewards(user_id,day_start_ts,reward_type,reward_amount) VALUES(%s,%s,'coins',1)",
            (a, day - n * 86400),
        )
    r = race(lambda _: activity.claim_milestone(a))
    assert sum(not x["already_claimed"] for x in r) == 1


@check
def event_draft_hidden_contribution_owned_and_goal_reward_once():
    admin = user()
    a = user(cards={C1: 1})
    b = user(cards={C2: 1})
    outsider = user()
    eid = events.create(admin, spec())["id"]
    assert not any(e["id"] == eid for e in events.listing(a)["items"])
    denied(lambda: events.contribute(a, eid, C1, key()), "event_closed")
    events.publish(admin, eid)
    denied(lambda: events.contribute(outsider, eid, C1, key()), "card_missing")
    rid = key()
    first = events.contribute(a, eid, C1, rid)
    assert events.contribute(a, eid, C1, rid) == first
    denied(lambda: events.claim(a, eid), "goal_pending")
    denied(lambda: events.contribute(a, eid, C1, key()), "already_contributed")
    events.contribute(b, eid, C2, key())
    assert events.claim(a, eid)["already_claimed"] is False
    assert events.claim(a, eid)["already_claimed"] is True
    denied(lambda: events.claim(outsider, eid), "goal_pending")
    assert qty(a, C1) == qty(b, C2) == 1


@check
def concurrent_event_contributions_obey_daily_limit():
    admin = user()
    a = user(cards={C1: 1, C2: 1})
    eid = events.create(admin, spec())["id"]
    events.publish(admin, eid)
    r = race(lambda i: events.contribute(a, eid, [C1, C2][i % 2], key()))
    assert sum(bool(x.get("ok")) for x in r) == 1


@check
def event_dates_and_catalog_are_validated_before_creating():
    a = user()
    value = spec()
    value["ends_at"] = value["starts_at"] + timedelta(days=30, seconds=1)
    denied(lambda: events.create(a, value), "invalid_dates")
    value = spec()
    value["character_ids"] = [2**53 - 1]
    denied(lambda: events.create(a, value), "invalid_characters")


@check
def inline_showcase_is_private_by_default_and_bounded():
    from commands.collecting import inline_cards

    a = user(cards={C1: 2})
    assert not inline_cards(a, "", 0)["items"]
    collection.save_settings(a, {"share_inline": True})
    assert inline_cards(a, "", 0)["items"][0]["id"] == C1
    assert not inline_cards(a, "", 100)["items"]


@check
def new_api_authentication_validation_and_all_gets():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from source_features import router

    a = user(cards={C1: 3})
    b = user()
    app = FastAPI()
    router.install(app)
    client = TestClient(app)
    prefix = "/api/v1_7b82/collecting"
    assert client.get(prefix + "/settings").status_code == 401

    def auth(value):
        if value == "Bearer synthetic-valid":
            return {"id": a}
        raise PermissionError("bad session")

    headers = {"Authorization": "Bearer synthetic-valid"}
    with (
        patch.object(router, "_require_user", side_effect=auth),
        patch.object(router, "is_admin", return_value=False),
    ):
        for path in [
            "/settings",
            "/characters",
            "/characters?view=wishes",
            "/characters?view=duplicates",
            "/characters?view=protected",
            "/characters?view=catalog",
            "/matches",
            "/workshop",
            "/cosmetics/profile",
            "/now",
            "/calendar",
            "/market",
            "/events",
            "/help",
            "/dice-info",
        ]:
            response = client.get(prefix + path, headers=headers)
            assert response.status_code == 200, (
                path,
                response.status_code,
                response.text[:500],
            )
        assert (
            client.patch(
                prefix + "/settings",
                headers=headers,
                json={"user_id": b, "share_inline": True},
            ).status_code
            == 422
        )
        assert (
            client.post(
                prefix + "/market",
                headers=headers,
                json={
                    "character_id": True,
                    "quantity": 1,
                    "price": 1,
                    "request_id": key(),
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                prefix + "/identify", headers=headers, content=b"no consent"
            ).status_code
            == 400
        )
        assert (
            client.post(
                prefix + "/events/" + key() + "/publish", headers=headers, json={}
            ).status_code
            == 403
        )
        assert (
            client.put(
                prefix + f"/characters/{C1}/protection",
                headers=headers,
                json={"enabled": True},
            ).status_code
            == 200
        )
        assert collection.cards(a, view="protected")["items"]
        assert not collection.cards(b, view="protected")["items"]


@check
def active_market_prevents_account_deletion_without_destroying_escrow():
    a = user(cards={C1: 3})
    mid = listing(a)
    denied(lambda: db.delete_user_account(a), "active_market")
    assert qty(a, C1) == 3 and record(mid)["status"] == "active"
    market.act(a, mid, "cancel", key(), 1)
    collection.set_protection(a, C1, True)
    db.delete_user_account(a)
    assert scalar("SELECT COUNT(*) FROM users WHERE user_id=%s", (a,)) == 0


out = Path(sys.argv[1] if len(sys.argv) > 1 else "collecting-transactions.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(
        {
            "passed": all(r["passed"] for r in results),
            "cases": results,
            "scope": "Disposable PostgreSQL; synthetic users; provider and Telegram deliveries not live.",
        },
        ensure_ascii=False,
        indent=2,
    )
)
pool.close()
raise SystemExit(0 if all(r["passed"] for r in results) else 1)
