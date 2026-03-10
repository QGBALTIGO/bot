import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import (
    add_progress_xp,
    add_user_coins,
    create_or_get_user,
    create_termo_game,
    ensure_termo_stats_row,
    finish_termo_game,
    get_termo_active_game,
    get_termo_daily_game,
    get_termo_global_ranking,
    get_termo_period_ranking,
    get_termo_stats,
    get_termo_user_rank,
    has_accepted_terms,
    has_user_used_termo_word,
    mark_termo_word_used,
    record_termo_result,
    touch_user_identity,
    update_termo_game_progress,
)

from utils.gatekeeper import TERMS_VERSION


WORDS_FILE = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json")
SP_TZ = ZoneInfo("America/Sao_Paulo")

TIME_LIMIT_SECONDS = 300
MAX_ATTEMPTS = 6
WORD_LENGTH = 6
ANTI_FLOOD_SECONDS = 1.5
XP_REWARD = 10

ADMIN_IDS: Set[int] = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

ACTIVE_GAMES: Dict[int, Dict[str, Any]] = {}
LAST_GUESS_AT: Dict[int, float] = {}
WORDS_CACHE: List[Dict[str, str]] = []
VALID_WORDS: Set[str] = set()


# =========================================================
# WORDS / TIME
# =========================================================

def _sp_now() -> datetime:
    return datetime.now(SP_TZ)


def _sp_today():
    return _sp_now().date()


def _next_reset_text() -> str:
    now = _sp_now()
    tomorrow = datetime.combine(
        (now + timedelta(days=1)).date(),
        datetime.min.time(),
        tzinfo=SP_TZ,
    )
    delta = tomorrow - now
    total = int(delta.total_seconds())
    hours = total // 3600
    minutes = (total % 3600) // 60
    return f"{hours}h {minutes}m"


def _valid_format(word: str) -> bool:
    word = (word or "").strip().lower()
    return bool(re.fullmatch(r"[a-záàâãéèêíìîóòôõúùûç]{6}", word))


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _load_words() -> List[Dict[str, str]]:
    global WORDS_CACHE, VALID_WORDS

    if WORDS_CACHE:
        return WORDS_CACHE

    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    cleaned: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue

        word = str(item.get("word", "")).strip().lower()
        category = str(item.get("category", "")).strip() or "Desconhecido"
        source = str(item.get("source", "")).strip() or "Anime"

        if not _valid_format(word):
            continue
        if word in seen:
            continue

        seen.add(word)
        cleaned.append({
            "word": word,
            "category": category,
            "source": source,
        })

    WORDS_CACHE = cleaned
    VALID_WORDS = {x["word"] for x in cleaned}
    return WORDS_CACHE


def _is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS


def _anti_flood_ok(user_id: int) -> bool:
    now = time.time()
    last = LAST_GUESS_AT.get(int(user_id), 0.0)
    if now - last < ANTI_FLOOD_SECONDS:
        return False
    LAST_GUESS_AT[int(user_id)] = now
    return True


def _seconds_left(start_time: int) -> int:
    return max(TIME_LIMIT_SECONDS - (int(time.time()) - int(start_time)), 0)


def _fmt_mmss(seconds: int) -> str:
    minutes = seconds // 60
    sec = seconds % 60
    return f"{minutes}:{sec:02d}"


# =========================================================
# USER / GATEKEEPER
# =========================================================

def _touch_identity_from_update(update: Update) -> None:
    user = update.effective_user
    if not user:
        return

    create_or_get_user(int(user.id))
    touch_user_identity(
        int(user.id),
        getattr(user, "username", "") or "",
        " ".join(
            p for p in [
                getattr(user, "first_name", "") or "",
                getattr(user, "last_name", "") or "",
            ] if p
        ).strip(),
    )


async def _gatekeeper_ok(update: Update) -> bool:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return False

    _touch_identity_from_update(update)

    if has_accepted_terms(int(user.id), TERMS_VERSION):
        return True

    await msg.reply_text(
        "❌ Você precisa aceitar os termos antes de usar o Termo.\n\n"
        "Use /start e conclua a etapa de aceite."
    )
    return False


# =========================================================
# GAME HELPERS
# =========================================================

def _daily_coins(attempts: int) -> int:
    if attempts == 1:
        return 10
    if attempts == 2:
        return 8
    if attempts == 3:
        return 6
    if attempts == 4:
        return 4
    return 2


def _streak_bonus(streak: int) -> int:
    if streak > 0 and streak % 30 == 0:
        return 50
    if streak > 0 and streak % 7 == 0:
        return 10
    if streak > 0 and streak % 3 == 0:
        return 5
    return 0


def _pick_daily_word(user_id: int) -> Dict[str, str]:
    words = _load_words()
    available = [w for w in words if not has_user_used_termo_word(user_id, w["word"])]
    pool = available if available else words
    rng = random.Random(f"{user_id}:{_sp_today().isoformat()}")
    return rng.choice(pool)


def _pick_train_word() -> Dict[str, str]:
    return random.choice(_load_words())


def _evaluate(secret: str, guess: str) -> str:
    result = ["⬛"] * WORD_LENGTH
    remaining: Dict[str, int] = {}

    for i in range(WORD_LENGTH):
        if guess[i] == secret[i]:
            result[i] = "🟩"
        else:
            remaining[secret[i]] = remaining.get(secret[i], 0) + 1

    for i in range(WORD_LENGTH):
        if result[i] == "🟩":
            continue
        ch = guess[i]
        if remaining.get(ch, 0) > 0:
            result[i] = "🟨"
            remaining[ch] -= 1

    return "".join(result)


def _used_letters(guesses: List[Dict[str, Any]]) -> str:
    correct: Set[str] = set()
    present: Set[str] = set()
    absent: Set[str] = set()

    for item in guesses:
        guess = str(item.get("guess", "")).lower()
        result = str(item.get("result", ""))

        for i, ch in enumerate(guess):
            if not ch.isalpha():
                continue

            marker = result[i] if i < len(result) else "⬛"

            if marker == "🟩":
                correct.add(ch.upper())
                present.discard(ch.upper())
                absent.discard(ch.upper())
            elif marker == "🟨":
                if ch.upper() not in correct:
                    present.add(ch.upper())
                    absent.discard(ch.upper())
            else:
                if ch.upper() not in correct and ch.upper() not in present:
                    absent.add(ch.upper())

    lines = []
    if correct:
        lines.append("🟩 " + " ".join(sorted(correct)))
    if present:
        lines.append("🟨 " + " ".join(sorted(present)))
    if absent:
        lines.append("⬛ " + " ".join(sorted(absent)))

    return "\n".join(lines) if lines else "-"


def _history_text(guesses: List[Dict[str, Any]]) -> str:
    if not guesses:
        return "⬛⬛⬛⬛⬛⬛"

    lines: List[str] = []
    for item in guesses:
        lines.append(str(item["guess"]).upper())
        lines.append(str(item["result"]))
        lines.append("")
    return "\n".join(lines).rstrip()


def _share_text(guesses: List[Dict[str, Any]], attempts: int, win: bool, streak: int) -> str:
    rows = [str(x["result"]) for x in guesses]
    grid = "\n".join(rows)
    score = f"{attempts}/6" if win else "X/6"

    return (
        "🎌 TERMO ANIME — SourceBaltigo\n\n"
        f"{grid}\n\n"
        f"{score}\n"
        f"🔥 Streak: {streak}"
    )


def _share_button(share_text: str) -> InlineKeyboardMarkup:
    url = f"https://t.me/share/url?text={quote_plus(share_text)}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Compartilhar no Telegram", url=url)]
    ])


def _display_name(row: Dict[str, Any]) -> str:
    username = (row.get("username") or "").strip()
    full_name = (row.get("full_name") or "").strip()

    if username:
        return f"@{username}"
    if full_name:
        return full_name
    return f"Usuário {int(row.get('user_id') or 0)}"


def _intro_text() -> str:
    return (
        "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b> relacionada ao mundo dos animes.\n\n"
        "🎯 6 tentativas\n"
        "⏱ 5 minutos para resolver\n"
        "🎁 Recompensa ao acertar\n\n"
        "🪙 Coins por desempenho\n"
        f"⭐ +{XP_REWARD} XP\n\n"
        "🟩 Letra correta na posição correta\n"
        "🟨 Letra existe mas posição errada\n"
        "⬛ Letra não existe\n\n"
        "A palavra renova todos os dias às 00:00 no horário de São Paulo."
    )


def _start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Iniciar Desafio", callback_data="termo:start")],
        [InlineKeyboardButton("📊 Estatísticas", callback_data="termo:stats")],
        [InlineKeyboardButton("🏆 Ranking", callback_data="termo:ranking")],
    ])


def _board_text(game: Dict[str, Any]) -> str:
    return (
        "🎌 <b>TERMO ANIME</b>\n\n"
        f"{_history_text(game['guesses'])}\n\n"
        f"Tentativas: <b>{len(game['guesses'])}/6</b>\n"
        f"Tempo restante: <b>{_fmt_mmss(_seconds_left(game['start_time']))}</b>\n\n"
        f"🔤 <b>Letras usadas:</b>\n{_used_letters(game['guesses']) or '-'}"
        + ("\n\n🧪 <b>Modo treino</b>" if game["mode"] == "train" else "")
    )


def _stats_text(user_id: int) -> str:
    ensure_termo_stats_row(user_id)

    stats = get_termo_stats(user_id) or {}
    rank = get_termo_user_rank(user_id)

    games = int(stats.get("games_played") or 0)
    wins = int(stats.get("wins") or 0)
    losses = int(stats.get("losses") or 0)
    current_streak = int(stats.get("current_streak") or 0)
    best_streak = int(stats.get("best_streak") or 0)
    best_score = int(stats.get("best_score") or 0)

    one_try = int(stats.get("one_try") or 0)
    two_try = int(stats.get("two_try") or 0)
    three_try = int(stats.get("three_try") or 0)
    four_try = int(stats.get("four_try") or 0)
    five_try = int(stats.get("five_try") or 0)
    six_try = int(stats.get("six_try") or 0)

    win_rate = int(round((wins / games) * 100)) if games > 0 else 0
    best_score_text = best_score if best_score > 0 else "-"

    return (
        "📊 <b>Estatísticas Termo</b>\n\n"
        f"🎮 Jogos: <b>{games}</b>\n"
        f"✅ Vitórias: <b>{wins}</b>\n"
        f"❌ Derrotas: <b>{losses}</b>\n"
        f"📈 Taxa de vitória: <b>{win_rate}%</b>\n\n"
        f"🔥 Streak atual: <b>{current_streak}</b>\n"
        f"🏆 Melhor streak: <b>{best_streak}</b>\n"
        f"🎯 Melhor score: <b>{best_score_text}</b>\n"
        f"🌍 Ranking global: <b>{rank if rank and rank > 0 else '-'}</b>\n\n"
        "📦 <b>Distribuição</b>\n"
        f"1 tentativa: <b>{one_try}</b>\n"
        f"2 tentativas: <b>{two_try}</b>\n"
        f"3 tentativas: <b>{three_try}</b>\n"
        f"4 tentativas: <b>{four_try}</b>\n"
        f"5 tentativas: <b>{five_try}</b>\n"
        f"6 tentativas: <b>{six_try}</b>"
    )


def _ranking_text(rows: List[Dict[str, Any]], title: str) -> str:
    if not rows:
        return f"🏆 <b>{title}</b>\n\nAinda não há resultados."

    lines = [f"🏆 <b>{title}</b>\n"]
    medals = ["1️⃣", "2️⃣", "3️⃣"]

    for i, row in enumerate(rows, start=1):
        icon = medals[i - 1] if i <= 3 else f"{i}."
        wins = int(row.get("wins") or 0)
        name = _display_name(row)

        if "best_streak" in row:
            best_streak = int(row.get("best_streak") or 0)
            best_score = int(row.get("best_score") or 0)
            lines.append(
                f"{icon} {name} — {wins} vitórias | 🔥 {best_streak} | 🎯 {best_score or '-'}"
            )
        else:
            avg = float(row.get("avg_attempts") or 0)
            if avg:
                lines.append(f"{icon} {name} — {wins} vitórias | média {avg:.2f}")
            else:
                lines.append(f"{icon} {name} — {wins} vitórias")

    return "\n".join(lines)


def _cache_from_db_row(row: Dict[str, Any]) -> Dict[str, Any]:
    guesses = row.get("guesses") or []
    if isinstance(guesses, str):
        try:
            guesses = json.loads(guesses)
        except Exception:
            guesses = []

    game = {
        "user_id": int(row["user_id"]),
        "date": row["date"],
        "word": str(row["word"]).lower(),
        "category": str(row.get("category") or "Desconhecido"),
        "source": str(row.get("source") or "Anime"),
        "guesses": guesses,
        "mode": str(row.get("mode") or "daily"),
        "status": str(row.get("status") or "playing"),
        "start_time": int(row["start_time"]),
    }
    ACTIVE_GAMES[int(game["user_id"])] = game
    return game


def _get_active_game(user_id: int) -> Optional[Dict[str, Any]]:
    cached = ACTIVE_GAMES.get(int(user_id))
    if cached and cached.get("status") == "playing":
        return cached

    row = get_termo_active_game(int(user_id))
    if not row:
        ACTIVE_GAMES.pop(int(user_id), None)
        return None

    return _cache_from_db_row(row)


def _persist_progress(game: Dict[str, Any]) -> None:
    if game.get("mode") == "train":
        return

    update_termo_game_progress(
        user_id=int(game["user_id"]),
        attempts=len(game["guesses"]),
        guesses_json=json.dumps(game["guesses"], ensure_ascii=False),
        used_letters=_used_letters(game["guesses"]),
    )


def _finish_game(game: Dict[str, Any], status: str, reward_coins: int = 0, reward_xp: int = 0) -> None:
    if game.get("mode") == "train":
        ACTIVE_GAMES.pop(int(game["user_id"]), None)
        return

    spent = max(0, int(time.time()) - int(game["start_time"]))
    finish_termo_game(
        user_id=int(game["user_id"]),
        status=status,
        attempts=len(game["guesses"]),
        guesses_json=json.dumps(game["guesses"], ensure_ascii=False),
        used_letters=_used_letters(game["guesses"]),
        time_spent_seconds=spent,
        reward_coins=reward_coins,
        reward_xp=reward_xp,
        won_at_attempt=len(game["guesses"]) if status == "win" else 0,
    )
    ACTIVE_GAMES.pop(int(game["user_id"]), None)


# =========================================================
# START / TRAIN
# =========================================================

async def _start_daily(update: Update, use_edit: bool = False) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    today = _sp_today()

    existing = get_termo_daily_game(user_id, today)

    if existing:
        if str(existing.get("status")) == "playing":
            game = _cache_from_db_row(existing)
            text = _board_text(game)
        else:
            text = (
                "❌ Você já jogou a palavra de hoje.\n\n"
                f"📅 Próxima palavra em <b>{_next_reset_text()}</b>."
            )

        if use_edit and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        else:
            await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    word_data = _pick_daily_word(user_id)
    start_ts = int(time.time())

    create_termo_game(
        user_id=user_id,
        game_date=today,
        word=word_data["word"],
        category=word_data["category"],
        source=word_data["source"],
        start_time=start_ts,
        mode="daily",
    )
    mark_termo_word_used(user_id, word_data["word"])

    ACTIVE_GAMES[user_id] = {
        "user_id": user_id,
        "date": today,
        "word": word_data["word"],
        "category": word_data["category"],
        "source": word_data["source"],
        "guesses": [],
        "mode": "daily",
        "status": "playing",
        "start_time": start_ts,
    }

    text = (
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras."
    )

    if use_edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML")


async def _start_train(update: Update, use_edit: bool = False) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    if not _is_admin(user_id):
        text = "❌ Apenas admins podem usar o modo treino."
        if use_edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return

    word_data = _pick_train_word()
    ACTIVE_GAMES[user_id] = {
        "user_id": user_id,
        "date": _sp_today(),
        "word": word_data["word"],
        "category": word_data["category"],
        "source": word_data["source"],
        "guesses": [],
        "mode": "train",
        "status": "playing",
        "start_time": int(time.time()),
    }

    text = (
        "🧪 <b>TERMO TREINO</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras."
    )

    if use_edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML")


# =========================================================
# COMMAND HANDLERS
# =========================================================

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    user_id = int(update.effective_user.id)
    game = _get_active_game(user_id)

    if game:
        await update.message.reply_text(_board_text(game), parse_mode="HTML")
        return

    await update.message.reply_text(
        _intro_text(),
        parse_mode="HTML",
        reply_markup=_start_buttons(),
    )


async def termo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _stats_text(int(update.effective_user.id)),
        parse_mode="HTML",
    )


async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
        parse_mode="HTML",
    )


async def termo_ranking_week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(7, 10), "Ranking Termo — Semana"),
        parse_mode="HTML",
    )


async def termo_ranking_month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(30, 10), "Ranking Termo — Mês"),
        parse_mode="HTML",
    )


async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await _start_train(update, use_edit=False)


async def termo_treino_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    user_id = int(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ Apenas admins podem usar isso.")
        return

    game = ACTIVE_GAMES.get(user_id)
    if not game or game.get("mode") != "train":
        await update.message.reply_text("❌ Nenhum treino ativo.")
        return

    await update.message.reply_text(_board_text(game), parse_mode="HTML")


async def termo_treino_stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    user_id = int(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ Apenas admins podem usar isso.")
        return

    game = ACTIVE_GAMES.get(user_id)
    if game and game.get("mode") == "train":
        ACTIVE_GAMES.pop(user_id, None)
        await update.message.reply_text("🧪 Treino encerrado.")
    else:
        await update.message.reply_text("❌ Nenhum treino ativo.")


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def termo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    _touch_identity_from_update(update)

    if not has_accepted_terms(int(query.from_user.id), TERMS_VERSION):
        await query.edit_message_text(
            "❌ Você precisa aceitar os termos antes de usar o Termo.\n\n"
            "Use /start e conclua a etapa de aceite."
        )
        return

    data = str(query.data or "")

    if data == "termo:start":
        await _start_daily(update, use_edit=True)
        return

    if data == "termo:stats":
        await query.edit_message_text(
            _stats_text(int(query.from_user.id)),
            parse_mode="HTML",
        )
        return

    if data == "termo:ranking":
        await query.edit_message_text(
            _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
            parse_mode="HTML",
        )
        return

    if data == "termo:train_start":
        await _start_train(update, use_edit=True)
        return


# =========================================================
# GUESS HANDLER
# =========================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    _touch_identity_from_update(update)

    if not has_accepted_terms(int(update.effective_user.id), TERMS_VERSION):
        return

    guess = _normalize(update.message.text)
    user_id = int(update.effective_user.id)

    if len(guess) != WORD_LENGTH:
        return
    if not _valid_format(guess):
        return

    _load_words()
    if guess not in VALID_WORDS:
        await update.message.reply_text("❌ Palavra inválida.")
        return

    game = _get_active_game(user_id)
    if not game:
        return

    if not _anti_flood_ok(user_id):
        return

    if guess in {str(x["guess"]).lower() for x in game["guesses"]}:
        await update.message.reply_text("❌ Palavra já usada.")
        return

    if _seconds_left(game["start_time"]) <= 0:
        training = game["mode"] == "train"
        if not training:
            record_termo_result(user_id, False, len(game["guesses"]))
        _finish_game(game, "timeout")

        await update.message.reply_text(
            "⏱ <b>Tempo esgotado!</b>\n\n"
            f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>\n\n"
            f"📅 Próxima palavra em <b>{_next_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    result = _evaluate(game["word"], guess)
    game["guesses"].append({
        "guess": guess,
        "result": result,
        "ts": int(time.time()),
    })
    _persist_progress(game)

    if guess == game["word"]:
        training = game["mode"] == "train"
        current_streak = 0
        reward_coins = 0
        bonus_coins = 0

        if not training:
            record_termo_result(user_id, True, len(game["guesses"]))
            stats = get_termo_stats(user_id) or {}
            current_streak = int(stats.get("current_streak") or 0)

            reward_coins = _daily_coins(len(game["guesses"]))
            bonus_coins = _streak_bonus(current_streak)

            add_user_coins(user_id, reward_coins + bonus_coins)
            add_progress_xp(user_id, XP_REWARD)

        share = _share_text(game["guesses"], len(game["guesses"]), True, current_streak)
        _finish_game(game, "win", reward_coins + bonus_coins, 0 if training else XP_REWARD)

        if training:
            await update.message.reply_text(
                "🎉 <b>Você acertou no modo treino!</b>\n\n"
                f"{_history_text(game['guesses'])}\n\n"
                f"Categoria: <b>{game['category']}</b>\n"
                f"Origem: <b>{game['source']}</b>\n\n"
                f"📤 <b>Compartilhe seu resultado:</b>\n<code>{share}</code>",
                parse_mode="HTML",
                reply_markup=_share_button(share),
            )
        else:
            bonus_text = f"\n🎁 Bônus de streak: <b>+{bonus_coins} Coins</b>" if bonus_coins > 0 else ""
            await update.message.reply_text(
                "🎉 <b>Você acertou!</b>\n\n"
                f"{_history_text(game['guesses'])}\n\n"
                f"Categoria: <b>{game['category']}</b>\n"
                f"Origem: <b>{game['source']}</b>\n\n"
                f"🪙 +<b>{reward_coins}</b> Coins\n"
                f"⭐ +<b>{XP_REWARD}</b> XP"
                f"{bonus_text}\n\n"
                f"🔥 Sequência atual: <b>{current_streak} dias</b>\n\n"
                f"📤 <b>Compartilhe seu resultado:</b>\n<code>{share}</code>",
                parse_mode="HTML",
                reply_markup=_share_button(share),
            )
        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:
        training = game["mode"] == "train"
        old_stats = get_termo_stats(user_id) or {}
        old_streak = int(old_stats.get("current_streak") or 0)

        if not training:
            record_termo_result(user_id, False, len(game["guesses"]))

        _finish_game(game, "lose")

        await update.message.reply_text(
            "❌ <b>Fim de jogo</b>\n\n"
            f"{_history_text(game['guesses'])}\n\n"
            f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>"
            + ("\n\n❌ <b>Sequência perdida!</b>" if old_streak > 0 and not training else "")
            + f"\n\n📅 Próxima palavra em <b>{_next_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(_board_text(game), parse_mode="HTML")
