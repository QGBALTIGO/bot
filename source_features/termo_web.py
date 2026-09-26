from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from database import xp_to_level
from database_core import pool
import commands.termo as termo

MAX_ATTEMPTS = termo.MAX_ATTEMPTS
TIME_LIMIT_SECS = termo.TIME_LIMIT_SECS
XP_REWARD = termo.XP_REWARD

TZ = ZoneInfo("America/Sao_Paulo")


def _today() -> date:
    return datetime.now(TZ).date()


def _public(row: dict | None) -> dict:
    if not row:
        return {"status": "idle", "guesses": [], "attempts": 0}
    guesses = list(row.get("guesses") or [])
    start = int(row.get("start_time") or 0)
    status = str(row.get("status") or "playing")
    out = {
        "id": int(row.get("id") or 0),
        "status": status,
        "attempts": len(guesses),
        "guesses": guesses,
        "category": str(row.get("category") or ""),
        "source": str(row.get("source") or ""),
        "seconds_left": max(0, TIME_LIMIT_SECS - (int(time.time()) - start)) if status == "playing" else 0,
    }
    if status != "playing":
        out["word"] = str(row.get("word") or "").upper()
        out["reward_coins"] = int(row.get("reward_coins") or 0)
        out["reward_xp"] = int(row.get("reward_xp") or 0)
    return out


def termo_state(user_id: int) -> dict:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM termo_games WHERE user_id=%s AND date=%s AND mode='daily' LIMIT 1",
                (int(user_id), _today()),
            )
            return _public(dict(cur.fetchone() or {}))


def termo_start(user_id: int) -> dict:
    uid = int(user_id)
    today = _today()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (uid,))
            cur.execute(
                "SELECT * FROM termo_games WHERE user_id=%s AND date=%s AND mode='daily' LIMIT 1 FOR UPDATE",
                (uid, today),
            )
            existing = cur.fetchone()
            if existing:
                conn.commit()
                return _public(dict(existing))
            word = termo._pick_daily_word(uid)
            cur.execute(
                """
                INSERT INTO termo_games(user_id,date,word,category,source,attempts,guesses,used_letters,status,mode,start_time)
                VALUES(%s,%s,%s,%s,%s,0,'[]'::jsonb,'','playing','daily',%s)
                RETURNING *
                """,
                (uid, today, word["word"], word["category"], word["source"], int(time.time())),
            )
            row = dict(cur.fetchone() or {})
            cur.execute(
                "INSERT INTO termo_used_words(user_id,word) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (uid, word["word"]),
            )
            conn.commit()
            return _public(row)


def _record_stats(cur, uid: int, win: bool, attempts: int) -> int:
    today = _today()
    cur.execute("INSERT INTO termo_stats(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))
    cur.execute("INSERT INTO termo_attempt_distribution(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))
    cur.execute("SELECT * FROM termo_stats WHERE user_id=%s FOR UPDATE", (uid,))
    row = dict(cur.fetchone() or {})
    streak = int(row.get("current_streak") or 0)
    best = int(row.get("best_streak") or 0)
    last = row.get("last_play_date")
    if win:
        yesterday = today.fromordinal(today.toordinal() - 1)
        streak = streak + 1 if last == yesterday else (max(streak, 1) if last == today else 1)
        best = max(best, streak)
        best_score = int(row.get("best_score") or 0)
        if best_score <= 0 or attempts < best_score:
            best_score = attempts
        cur.execute(
            """UPDATE termo_stats SET games_played=games_played+1,wins=wins+1,current_streak=%s,
               best_streak=%s,best_score=%s,last_play_date=%s,updated_at=NOW() WHERE user_id=%s""",
            (streak, best, best_score, today, uid),
        )
        cols = {1:"one_try",2:"two_try",3:"three_try",4:"four_try",5:"five_try",6:"six_try"}
        col = cols.get(attempts)
        if col:
            cur.execute(f"UPDATE termo_attempt_distribution SET {col}={col}+1 WHERE user_id=%s", (uid,))
    else:
        cur.execute(
            """UPDATE termo_stats SET games_played=games_played+1,losses=losses+1,current_streak=0,
               last_play_date=%s,updated_at=NOW() WHERE user_id=%s""",
            (today, uid),
        )
        streak = 0
    return streak


def _award(cur, uid: int, coins: int, xp: int) -> None:
    cur.execute("INSERT INTO users(user_id,coins,created_at,updated_at) VALUES(%s,0,NOW(),NOW()) ON CONFLICT DO NOTHING", (uid,))
    if coins:
        cur.execute("UPDATE users SET coins=coins+%s,updated_at=NOW() WHERE user_id=%s", (coins, uid))
    cur.execute(
        """INSERT INTO user_progress(user_id,xp,level,total_actions,updated_at)
           VALUES(%s,%s,1,1,NOW())
           ON CONFLICT(user_id) DO UPDATE SET xp=user_progress.xp+EXCLUDED.xp,
             total_actions=user_progress.total_actions+1,updated_at=NOW()
           RETURNING xp""",
        (uid, xp),
    )
    total_xp = int((cur.fetchone() or {}).get("xp") or 0)
    cur.execute("UPDATE user_progress SET level=%s WHERE user_id=%s", (xp_to_level(total_xp), uid))


def termo_guess(user_id: int, guess: str) -> dict:
    uid = int(user_id)
    guess = str(guess or "").strip().lower()
    termo._load_words()
    if len(guess) != 6 or guess not in termo.VALID_WORDS:
        return {"ok": False, "error": "invalid_word"}

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM termo_games WHERE user_id=%s AND date=%s AND mode='daily' LIMIT 1 FOR UPDATE",
                (uid, _today()),
            )
            row = dict(cur.fetchone() or {})
            if not row:
                conn.rollback()
                return {"ok": False, "error": "not_started"}
            if str(row.get("status")) != "playing":
                conn.commit()
                return {"ok": True, "game": _public(row), "already_done": True}
            guesses = list(row.get("guesses") or [])
            if any(str(item.get("guess") or "") == guess for item in guesses):
                conn.rollback()
                return {"ok": False, "error": "already_guessed"}
            elapsed = int(time.time()) - int(row.get("start_time") or 0)
            if elapsed >= TIME_LIMIT_SECS:
                _record_stats(cur, uid, False, len(guesses))
                cur.execute("UPDATE termo_games SET status='timeout',finished_at=NOW(),updated_at=NOW() WHERE id=%s", (int(row["id"]),))
                conn.commit()
                row["status"] = "timeout"
                return {"ok": True, "game": _public(row)}

            result = termo._evaluate(str(row["word"]), guess)
            guesses.append({"guess": guess, "result": result, "ts": int(time.time())})
            attempts = len(guesses)
            status = "playing"
            coins = xp = 0
            if guess == str(row["word"]):
                status = "win"
                streak = _record_stats(cur, uid, True, attempts)
                coins = termo._daily_coins(attempts) + termo._streak_bonus(streak)
                xp = XP_REWARD
                _award(cur, uid, coins, xp)
            elif attempts >= MAX_ATTEMPTS:
                status = "lose"
                _record_stats(cur, uid, False, attempts)

            cur.execute(
                """UPDATE termo_games SET attempts=%s,guesses=%s::jsonb,used_letters=%s,status=%s,
                   reward_coins=%s,reward_xp=%s,finished_at=CASE WHEN %s='playing' THEN finished_at ELSE NOW() END,
                   won_at_attempt=CASE WHEN %s='win' THEN %s ELSE 0 END,updated_at=NOW() WHERE id=%s RETURNING *""",
                (attempts, json.dumps(guesses, ensure_ascii=False), "".join(sorted({ch.upper() for g in guesses for ch in str(g["guess"])})),
                 status, coins, xp, status, status, attempts, int(row["id"])),
            )
            updated = dict(cur.fetchone() or {})
            conn.commit()
            return {"ok": True, "game": _public(updated)}
