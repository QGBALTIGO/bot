"""Exercise real transactions against an explicitly named disposable local database.

This program refuses production database hosts. No Telegram/API credentials are used.
The only patched business input is the randomized game prize, made deterministic.
"""
from __future__ import annotations
import itertools
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
url = os.environ.get('SOURCE_AUDIT_DATABASE_URL', '')
parsed = urlparse(url)
if parsed.hostname not in {'127.0.0.1', 'localhost', 'postgres'} or parsed.path != '/source_audit':
    raise SystemExit('Refusing anything except disposable localhost/source_audit')
os.environ.update(DATABASE_URL=url, BOT_TOKEN='999999999:synthetic-audit-not-a-valid-token')
from database_core import run, pool
import database as db
import database_shop_safety as shop
import database_aninexus_social as social
import database_aninexus_games as games
from database_profile import set_profile_nickname
from webapp_routes.native_webapps import change_nickname_atomic
from fastapi import HTTPException

db.create_tables()
ids = itertools.count(99100001)
results = []

def user(coins=10, dado=5):
    uid = next(ids)
    db.create_or_get_user(uid)
    run('UPDATE users SET coins=%s,dado_balance=%s,dado_slot=%s WHERE user_id=%s',
        (coins, dado, db._slot_number_from_dt(db._now_sp()), uid))
    return uid

def account(uid):
    return run('SELECT coins,dado_balance FROM users WHERE user_id=%s', (uid,), fetch='one')

def scalar(sql, params=()):
    return next(iter(run(sql, params, fetch='one').values()))

def race(fn, n=10):
    barrier = Barrier(n)
    def call(i):
        barrier.wait(timeout=10)
        return fn(i)
    with ThreadPoolExecutor(max_workers=n) as executor:
        return list(executor.map(call, range(n), timeout=35))

def check(fn):
    started = time.perf_counter()
    try:
        fn()
        result = {'case': fn.__name__, 'passed': True}
    except Exception as exc:
        result = {'case': fn.__name__, 'passed': False, 'error': type(exc).__name__,
                  'detail': str(exc), 'trace': traceback.format_exc()}
    result['ms'] = round((time.perf_counter()-started)*1000, 2)
    results.append(result)

@check
def simultaneous_sale_does_not_duplicate_coins():
    uid = user(); db.add_card_copy(uid, 601)
    r = race(lambda _: db.sell_character(uid, 601))
    assert sum(x['ok'] for x in r) == 1, r
    assert db.get_user_card_quantity(uid, 601) == 0
    assert account(uid)['coins'] == 11
    assert scalar('SELECT COUNT(*) FROM shop_card_sales WHERE user_id=%s', (uid,)) == 1
    assert scalar('SELECT COUNT(*) FROM shop_transactions WHERE user_id=%s', (uid,)) == 1

@check
def sale_rolls_back_card_and_coins_when_ledger_fails():
    uid = user(); db.add_card_copy(uid, 602)
    with patch.object(shop, '_ledger', side_effect=RuntimeError('injected failure')):
        try:
            db.sell_character(uid, 602)
            raise AssertionError('expected injected failure')
        except RuntimeError:
            pass
    assert account(uid)['coins'] == 10
    assert db.get_user_card_quantity(uid, 602) == 1
    assert scalar('SELECT COUNT(*) FROM shop_card_sales WHERE user_id=%s', (uid,)) == 0

@check
def buyback_one_use_even_under_concurrent_requests():
    uid = user(); db.add_card_copy(uid, 603)
    sale = db.sell_character(uid, 603)
    r = race(lambda _: db.buyback_character(uid, sale['sale_id']))
    assert sum(x['ok'] for x in r) == 1, r
    assert account(uid)['coins'] == 8
    assert db.get_user_card_quantity(uid, 603) == 1

@check
def buyback_rejects_other_owner_expired_and_insufficient_funds():
    uid, other = user(0), user(50); db.add_card_copy(uid, 604)
    sale = db.sell_character(uid, 604); sid = sale['sale_id']
    assert not db.buyback_character(other, sid)['ok']
    assert db.buyback_character(uid, sid)['error'] == 'no_coins'
    run("UPDATE shop_card_sales SET buyback_available_until=NOW()-INTERVAL '1 second' WHERE id=%s", (sid,))
    assert db.buyback_character(uid, sid)['error'] == 'sale_unavailable'
    assert account(other)['coins'] == 50 and db.get_user_card_quantity(other,604)==0

@check
def buyback_rolls_back_on_ledger_failure():
    uid = user(); db.add_card_copy(uid, 605); sale = db.sell_character(uid, 605)
    with patch.object(shop, '_ledger', side_effect=RuntimeError('injected failure')):
        try: db.buyback_character(uid, sale['sale_id'])
        except RuntimeError: pass
        else: raise AssertionError('expected failure')
    assert account(uid)['coins'] == 11 and db.get_user_card_quantity(uid,605)==0
    assert db.buyback_character(uid, sale['sale_id'])['ok']

@check
def concurrent_dado_purchase_never_spends_more_than_balance():
    uid = user(3, 1)
    r = race(lambda _: db.buy_dado(uid))
    assert sum(x['ok'] for x in r) == 1, r
    assert account(uid) == {'coins': 1, 'dado_balance': 2}

@check
def natural_recharge_to_full_is_applied_before_purchase_charge():
    uid = user(10, 23)
    run('UPDATE users SET dado_slot=dado_slot-1 WHERE user_id=%s', (uid,))
    r = db.buy_dado(uid)
    assert r['error']=='dado_full', r
    assert account(uid)=={'coins':10,'dado_balance':24}
    assert scalar('SELECT COUNT(*) FROM shop_transactions WHERE user_id=%s', (uid,))==0

@check
def concurrent_purchase_respects_dado_capacity():
    uid = user(100,23)
    r = race(lambda _: db.buy_dado(uid))
    assert sum(x['ok'] for x in r)==1, r
    assert account(uid)=={'coins':98,'dado_balance':24}

@check
def new_user_dado_initialization_is_concurrency_safe():
    uid = next(ids)
    r = race(lambda _: db.get_dado_state(uid))
    assert {x['balance'] for x in r}=={db.DADO_INITIAL_BALANCE}
    assert scalar('SELECT COUNT(*) FROM users WHERE user_id=%s',(uid,))==1

@check
def nickname_empty_request_cannot_charge():
    uid = user()
    assert not db.buy_nickname_change(uid)['ok']
    assert account(uid)['coins']==10

@check
def nickname_casefold_uniqueness_across_free_and_paid_paths():
    a,b=user(),user()
    barrier=Barrier(2)
    def first(): barrier.wait(); return set_profile_nickname(a,'Auditnameone')
    def second():
        barrier.wait()
        try: return change_nickname_atomic(b,'AUDITNAMEONE')
        except HTTPException as e: return {'ok':False,'status':e.status_code}
    with ThreadPoolExecutor(max_workers=2) as ex:
        x,y=ex.submit(first),ex.submit(second); r=[x.result(20),y.result(20)]
    assert sum(bool(x.get('ok')) for x in r)==1,r
    assert scalar('SELECT COUNT(*) FROM user_profile_settings WHERE lower(nickname)=lower(%s)',('Auditnameone',))==1
    assert account(b)['coins']==(7 if r[1].get('ok') else 10)

@check
def free_nickname_cannot_be_reset_by_racing_requests():
    uid=user()
    r=race(lambda i:set_profile_nickname(uid, f'Nameaudit{i}'))
    assert sum(x['ok'] for x in r)==1, r
    assert account(uid)['coins']==10

@check
def trade_rejects_forged_owner_and_protects_reserved_cards():
    a,b,c=user(),user(),user();db.add_card_copy(a,701);db.add_card_copy(b,702)
    trade=social.create_trade_offer(a,b,701,702);tid=trade['trade_id']
    assert not social.respond_trade_offer(c,tid,'accept')['ok']
    assert db.sell_character(a,701)['error']=='card_reserved'
    assert not social.create_trade_offer(a,b,701,702)['ok']
    assert social.respond_trade_offer(b,tid,'accept')['ok']
    assert db.get_user_card_quantity(a,702)==1 and db.get_user_card_quantity(b,701)==1

@check
def concurrent_trade_acceptance_moves_each_card_once():
    a,b=user(),user();db.add_card_copy(a,703);db.add_card_copy(b,704)
    tid=db.create_trade(a,b,703,704)
    r=race(lambda _:social.respond_trade_offer(b,tid,'accept'))
    assert sum(x['ok'] for x in r)==1,r
    assert (db.get_user_card_quantity(a,703),db.get_user_card_quantity(a,704),db.get_user_card_quantity(b,703),db.get_user_card_quantity(b,704))==(0,1,1,0)
    assert not db.swap_characters_atomic(tid)

@check
def rejected_or_expired_trade_cannot_be_revived():
    a,b=user(),user();db.add_card_copy(a,705);db.add_card_copy(b,706)
    tid=social.create_trade_offer(a,b,705,706)['trade_id']
    assert social.respond_trade_offer(b,tid,'reject')['ok']
    db.set_trade_status(tid,'pending')
    assert not social.respond_trade_offer(b,tid,'accept')['ok']
    tid=social.create_trade_offer(a,b,705,706)['trade_id']
    run("UPDATE card_trades SET created_at=NOW()-INTERVAL '25 hours' WHERE trade_id=%s",(tid,))
    assert social.respond_trade_offer(b,tid,'accept')['error']=='trade_expired'
    assert db.get_user_card_quantity(a,705)==1 and db.get_user_card_quantity(b,706)==1

@check
def simultaneous_accept_and_reject_has_one_terminal_state():
    a,b=user(),user();db.add_card_copy(a,707);db.add_card_copy(b,708)
    tid=social.create_trade_offer(a,b,707,708)['trade_id']
    r=race(lambda i:social.respond_trade_offer(b,tid,'accept' if i%2 else 'reject'))
    assert sum(x['ok'] for x in r)==1,r
    assert sum(db.get_user_card_quantity(uid,cid) for uid in (a,b) for cid in (707,708))==2

@check
def trade_rolls_back_if_recipient_delivery_fails():
    a,b=user(),user();db.add_card_copy(a,709);db.add_card_copy(b,710)
    tid=social.create_trade_offer(a,b,709,710)['trade_id']
    with patch.object(social,'_add_one_locked',side_effect=RuntimeError('injected delivery failure')):
        try:social.respond_trade_offer(b,tid,'accept')
        except RuntimeError:pass
        else:raise AssertionError('expected failure')
    assert db.get_user_card_quantity(a,709)==1 and db.get_user_card_quantity(b,710)==1
    assert social.respond_trade_offer(b,tid,'accept')['ok']

@check
def game_start_charges_energy_only_once():
    uid=user()
    def payload(_): return {'start_time':time.time()-10,'prize':{'type':'xp','amount':3},'prize_index':0}
    with patch.object(games,'_build_session_payload',side_effect=payload):
        r=race(lambda _:games.start_game_session(uid,'nexus_wheel'))
    assert all(x['ok'] for x in r),r
    assert len({x['session']['session_id'] for x in r})==1
    assert scalar('SELECT energy FROM aninexus_game_state WHERE user_id=%s',(uid,))==4

@check
def game_reward_is_owner_bound_and_idempotent():
    uid,other=user(),user()
    with patch.object(games,'_build_session_payload',return_value={'start_time':time.time()-10,'prize':{'type':'coins','amount':1},'prize_index':2}):
        sid=games.start_game_session(uid,'nexus_wheel')['session']['session_id']
    assert not games.submit_game_session(other,'nexus_wheel',sid)['ok']
    r=race(lambda _:games.submit_game_session(uid,'nexus_wheel',sid))
    assert all(x['ok'] for x in r),r
    assert sum(not x.get('already_done') for x in r)==1,r
    assert account(uid)['coins']==11 and account(other)['coins']==10
    assert scalar("SELECT COUNT(*) FROM shop_transactions WHERE user_id=%s AND type='aninexus_game_reward'",(uid,))==1

@check
def xp_progress_uses_level_relative_values():
    from webapp_routes.aninexus_compat import _user_payload
    uid=user()
    run('INSERT INTO user_progress (user_id,xp,level) VALUES (%s,1321,4) ON CONFLICT(user_id) DO UPDATE SET xp=1321,level=4',(uid,))
    result=_user_payload({'id':uid,'first_name':'Audit'})
    expected=db.get_level_progress_values(1321)
    stats=result['stats']
    assert stats['xp_current']==expected['xp_current'] and stats['xp_needed']==expected['xp_needed'],stats
    assert stats['xp_current'] < stats['xp_needed']

@check
def pet_purchase_and_activation_are_serialized():
    import database_aninexus_pets as pets
    uid=user(100)
    run('INSERT INTO user_progress(user_id,xp,level) VALUES (%s,20000,20) ON CONFLICT(user_id) DO UPDATE SET xp=20000,level=20',(uid,))
    r=race(lambda _:pets.buy_pet(uid,'blaze_fang'))
    assert sum(x['ok'] for x in r)==1,r
    assert account(uid)['coins']==97
    r=race(lambda i:pets.set_active_pet(uid,'blaze_fang' if i%2 else 'fluffy_fox'))
    assert all(x['ok'] for x in r),r
    assert scalar('SELECT COUNT(*) FROM aninexus_user_pets WHERE user_id=%s AND is_active',(uid,))==1

@check
def pet_care_cooldown_does_not_double_charge():
    import database_aninexus_pets as pets
    uid=user(10)
    r=race(lambda _:pets.care_for_active_pet(uid,'feed'))
    assert sum(x['ok'] for x in r)==1,r
    assert account(uid)['coins']==9
    r=race(lambda _:pets.care_for_active_pet(uid,'train'))
    assert sum(x['ok'] for x in r)==1,r

@check
def different_eggs_cannot_overbook_one_incubation_slot():
    import database_aninexus_pets as pets
    uid=user()
    pets.get_user_eggs(uid)
    ids=[pets.grant_egg(uid,'common')['egg_id'] for _ in range(10)]
    r=race(lambda i:pets.incubate_egg(uid,ids[i]))
    assert sum(x['ok'] for x in r)==1,r
    assert scalar("SELECT COUNT(*) FROM aninexus_user_eggs WHERE user_id=%s AND status='incubating'",(uid,))==1

@check
def egg_sale_and_hatch_are_owner_bound_and_one_use():
    import database_aninexus_pets as pets
    uid,other=user(),user()
    pets.get_user_eggs(uid)
    egg=pets.grant_egg(uid,'common')['egg_id']
    assert not pets.sell_egg(other,egg)['ok']
    r=race(lambda _:pets.sell_egg(uid,egg))
    assert sum(x['ok'] for x in r)==1,r
    assert account(uid)['coins']==11
    egg=pets.grant_egg(uid,'common')['egg_id']
    assert pets.incubate_egg(uid,egg)['ok']
    assert not pets.hatch_egg(other,egg)['ok']
    assert not pets.hatch_egg(uid,egg)['ok']
    run("UPDATE aninexus_user_eggs SET hatch_at=NOW()-INTERVAL '1 second' WHERE egg_id=%s",(egg,))
    with patch.object(pets,'_candidate_character_ids',return_value=[801]):
        r=race(lambda _:pets.hatch_egg(uid,egg))
    assert sum(x['ok'] for x in r)==1,r
    assert db.get_user_card_quantity(uid,801)==1



def hint_game(uid, *, expired=False):
    return scalar("INSERT INTO termo_games(user_id,date,word,start_time) VALUES (%s,CURRENT_DATE,'naruto',EXTRACT(EPOCH FROM NOW())::bigint-%s) RETURNING id", (uid, 600 if expired else 0))

@check
def termo_hint_concurrent_requests_charge_only_once():
    uid = user(coins=20); gid = hint_game(uid)
    r = race(lambda _: shop.purchase_termo_hint_atomic(uid, gid))
    assert all(x['ok'] for x in r), r
    assert sum(bool(x['charged']) for x in r) == 1
    assert account(uid)['coins'] == 8
    assert scalar("SELECT COUNT(*) FROM shop_transactions WHERE user_id=%s AND type='termo_hint'", (uid,)) == 1

@check
def termo_hint_insufficient_funds_never_go_negative():
    uid = user(coins=5); gid = hint_game(uid)
    assert shop.purchase_termo_hint_atomic(uid, gid)['error'] == 'no_coins'
    assert account(uid)['coins'] == 5

@check
def termo_hint_rejects_wrong_owner_expired_and_finished_game():
    uid, other = user(coins=20), user(coins=20); gid = hint_game(uid)
    assert not shop.purchase_termo_hint_atomic(other, gid)['ok']
    run("UPDATE termo_games SET status='won' WHERE id=%s", (gid,))
    assert not shop.purchase_termo_hint_atomic(uid, gid)['ok']
    expired_uid = user(coins=20); expired_gid = hint_game(expired_uid, expired=True)
    assert not shop.purchase_termo_hint_atomic(expired_uid, expired_gid)['ok']
    assert account(uid)['coins'] == account(other)['coins'] == account(expired_uid)['coins'] == 20

@check
def termo_hint_ledger_failure_rolls_back_debit():
    uid = user(coins=20); gid = hint_game(uid)
    with patch.object(shop, '_ledger', side_effect=RuntimeError('injected failure')):
        try:
            shop.purchase_termo_hint_atomic(uid, gid)
            raise AssertionError('expected injected failure')
        except RuntimeError:
            pass
    assert account(uid)['coins'] == 20

out=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/source-audit-transactions.json')
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'database':'disposable PostgreSQL','cases':results,'passed':all(x['passed'] for x in results)},ensure_ascii=False,indent=2))
pool.close()
print(json.dumps({'passed':sum(x['passed'] for x in results),'total':len(results)}))
raise SystemExit(0 if all(x['passed'] for x in results) else 1)
