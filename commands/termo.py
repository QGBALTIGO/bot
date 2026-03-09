import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

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
    has_user_used_termo_word,
    mark_termo_word_used,
    record_termo_result,
    update_termo_game_progress,
)

WORDS_FILE = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json")
TIME_LIMIT_SECONDS = 5 * 60
MAX_ATTEMPTS = 6
WORD_LENGTH = 6
ANTI_FLOOD_SECONDS = 2.0

XP_REWARD = 10

ADMIN_IDS: Set[int] = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

ACTIVE_GAMES: Dict[int, Dict[str, Any]] = {}
LAST_GUESS_AT: Dict[int, float] = {}
WORDS_CACHE: List[Dict[str, str]] = []
VALID_WORDS_SET: Set[str] = set()


def _load_words() -> List[Dict[str, str]]:
    global WORDS_CACHE, VALID_WORDS_SET

    if WORDS_CACHE:
        return WORDS_CACHE

    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    clean: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue

        word = str(item.get("word", "")).strip().lower()
        category = str(item.get("category", "")).strip() or "Desconhecido"
        source = str(item.get("source", "")).strip() or "Anime"

        if not _is_valid_word_format(word):
            continue

        if word in seen:
            continue

        seen.add(word)
        clean.append({
            "word": word,
            "category": category,
            "source": source,
        })

    WORDS_CACHE = clean
    VALID_WORDS_SET = {w["word"] for w in clean}
    return WORDS_CACHE


def _is_valid_word_format(word: str) -> bool:
    word = (word or "").strip().lower()
    if len(word) != WORD_LENGTH:
        return False
    if not re.fullmatch(r"[a-záàâãéèêíìîóòôõúùûç]+", word):
        return False
    return True


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def _anti_flood_ok(user_id: int) -> bool:
    now = time.time()
    last = LAST_GUESS_AT.get(int(user_id), 0.0)
    if now - last < ANTI_FLOOD_SECONDS:
        return False
    LAST_GUESS_AT[int(user_id)] = now
    return True


def _is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS


def _today() -> date:
    return date.today()


def _seconds_left(start_time: int) -> int:
    elapsed = int(time.time()) - int(start_time)
    return max(TIME_LIMIT_SECONDS - elapsed, 0)


def _format_mmss(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def _next_reset_text() -> str:
    now = datetime.now()
    tomorrow = datetime.combine((now + timedelta(days=1)).date(), datetime.min.time())
    delta = tomorrow - now
    total = int(delta.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    return f"{h}h {m}m"


def _daily_coins_for_attempt(attempts: int) -> int:
    attempts = int(attempts)
    if attempts == 1:
        return 10
    if attempts == 2:
        return 8
    if attempts == 3:
        return 6
    if attempts == 4:
        return 4
    return 2


def _streak_bonus(current_streak: int) -> int:
    if current_streak > 0 and current_streak % 30 == 0:
        return 50
    if current_streak > 0 and current_streak % 7 == 0:
        return 10
    if current_streak > 0 and current_streak % 3 == 0:
        return 5
    return 0


def _pick_daily_word(user_id: int) -> Dict[str, str]:
    words = _load_words()
    if not words:
        raise RuntimeError("TERMO_WORDS_FILE vazio ou inválido.")

    unused = [w for w in words if not has_user_used_termo_word(int(user_id), w["word"])]
    pool = unused if unused else words

    rng = random.Random(f"{int(user_id)}:{_today().isoformat()}")
    return rng.choice(pool)


def _pick_training_word() -> Dict[str, str]:
    words = _load_words()
    if not words:
        raise RuntimeError("TERMO_WORDS_FILE vazio ou inválido.")
    return random.choice(words)


def _evaluate_guess(secret: str, guess: str) -> str:
    secret = secret.lower()
    guess = guess.lower()

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
    seen: Set[str] = set()
    ordered: List[str] = []

    for item in guesses:
        guess = str(item.get("guess", "")).upper()
        for ch in guess:
            if ch.isalpha() and ch not in seen:
                seen.add(ch)
                ordered.append(ch)

    return " ".join(ordered)


def _history_text(guesses: List[Dict[str, Any]]) -> str:
    if not guesses:
        return "⬛⬛⬛⬛⬛⬛"

    parts: List[str] = []
    for item in guesses:
        parts.append(str(item.get("guess", "")).upper())
        parts.append(str(item.get("result", "")))
        parts.append("")

    return "\n".join(parts).rstrip()


def _keyboard_visual(guesses: List[Dict[str, Any]]) -> str:
    status: Dict[str, str] = {}
    priority = {"⬛": 0, "🟨": 1, "🟩": 2}

    for item in guesses:
        guess = str(item.get("guess", "")).upper()
        result = str(item.get("result", ""))
        for ch, mark in zip(guess, result):
            old = status.get(ch)
            if old is None or priority.get(mark, 0) > priority.get(old, 0):
                status[ch] = mark

    rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
    rendered: List[str] = []

    for row in rows:
        out: List[str] = []
        for ch in row:
            mark = status.get(ch)
            if mark == "🟩":
                out.append(f"🟩{ch}")
            elif mark == "🟨":
                out.append(f"🟨{ch}")
            elif mark == "⬛":
                out.append(f"⬛{ch}")
            else:
                out.append(f"▫️{ch}")
        rendered.append(" ".join(out))

    return "\n".join(rendered)


def _share_text(guesses: List[Dict[str, Any]], attempts: int, win: bool, streak: int, training: bool = False) -> str:
    rows = [str(item.get("result", "")) for item in guesses]
    grid = "\n".join(rows) if rows else "⬛⬛⬛⬛⬛⬛"
    score = f"{attempts}/6" if win else "X/6"
    suffix = " (Treino)" if training else ""

    return (
        f"🎌 TERMO ANIME — SourceBaltigo{suffix}\n\n"
        f"{grid}\n\n"
        f"{score}\n"
        f"🔥 Streak: {streak}"
    )


def _user_display_name(user) -> str:
    if getattr(user, "username", None):
        return f"@{user.username}"
    if getattr(user, "first_name", None):
        return user.first_name
    return str(getattr(user, "id", "Usuário"))


def _cache_game_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    guesses = row.get("guesses") or []
    if isinstance(guesses, str):
        try:
            guesses = json.loads(guesses)
        except Exception:
            guesses = []

    game = {
        "user_id": int(row["user_id"]),
        "date": row.get("date"),
        "word": str(row.get("word", "")).lower(),
        "category": str(row.get("category") or "Desconhecido"),
        "source": str(row.get("source") or "Anime"),
        "attempts": int(row.get("attempts") or 0),
        "guesses": guesses,
        "used_letters": str(row.get("used_letters") or ""),
        "status": str(row.get("status") or "playing"),
        "mode": str(row.get("mode") or "daily"),
        "start_time": int(row.get("start_time") or int(time.time())),
    }
    ACTIVE_GAMES[game["user_id"]] = game
    return game


def _get_active_game(user_id: int) -> Optional[Dict[str, Any]]:
    user_id = int(user_id)

    game = ACTIVE_GAMES.get(user_id)
    if game and game.get("status") == "playing":
        return game

    row = get_termo_active_game(user_id)
    if not row:
        ACTIVE_GAMES.pop(user_id, None)
        return None

    return _cache_game_from_row(row)


def _save_progress(game: Dict[str, Any]) -> None:
    game["attempts"] = len(game["guesses"])
    game["used_letters"] = _used_letters(game["guesses"])

    update_termo_game_progress(
        user_id=int(game["user_id"]),
        attempts=int(game["attempts"]),
        guesses_json=json.dumps(game["guesses"], ensure_ascii=False),
        used_letters=str(game["used_letters"]),
    )
    ACTIVE_GAMES[int(game["user_id"])] = game


def _finish_current_game(
    game: Dict[str, Any],
    status: str,
    reward_coins: int = 0,
    reward_xp: int = 0,
) -> None:
    game["status"] = status
    game["attempts"] = len(game["guesses"])
    game["used_letters"] = _used_letters(game["guesses"])

    spent = max(0, int(time.time()) - int(game["start_time"]))
    won_at_attempt = int(game["attempts"]) if status == "win" else 0

    finish_termo_game(
        user_id=int(game["user_id"]),
        status=status,
        attempts=int(game["attempts"]),
        guesses_json=json.dumps(game["guesses"], ensure_ascii=False),
        used_letters=str(game["used_letters"]),
        time_spent_seconds=spent,
        reward_coins=int(reward_coins),
        reward_xp=int(reward_xp),
        won_at_attempt=won_at_attempt,
    )

    ACTIVE_GAMES.pop(int(game["user_id"]), None)


def _stats_text(user_id: int) -> str:
    ensure_termo_stats_row(int(user_id))
    stats = get_termo_stats(int(user_id)) or {}
    rank = get_termo_user_rank(int(user_id))

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
    best_score_text = str(best_score) if best_score > 0 else "-"

    return (
        "📊 <b>Estatísticas Termo</b>\n\n"
        f"🎮 Jogos: <b>{games}</b>\n"
        f"✅ Vitórias: <b>{wins}</b>\n"
        f"❌ Derrotas: <b>{losses}</b>\n"
        f"📈 Taxa de vitória: <b>{win_rate}%</b>\n\n"
        f"🔥 Streak atual: <b>{current_streak}</b>\n"
        f"🏆 Melhor streak: <b>{best_streak}</b>\n"
        f"🎯 Melhor score: <b>{best_score_text}</b>\n"
        f"🌍 Ranking global: <b>{rank if rank > 0 else '-'}</b>\n\n"
        "📦 <b>Distribuição de vitórias</b>\n"
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

    medals = ["1️⃣", "2️⃣", "3️⃣"]
    lines = [f"🏆 <b>{title}</b>\n"]

    for idx, row in enumerate(rows, start=1):
        icon = medals[idx - 1] if idx <= 3 else f"{idx}."
        user_id = int(row.get("user_id") or 0)
        wins = int(row.get("wins") or 0)

        if "best_streak" in row:
            best_streak = int(row.get("best_streak") or 0)
            best_score = int(row.get("best_score") or 0)
            best_score_text = best_score if best_score > 0 else "-"
            lines.append(
                f"{icon} <code>{user_id}</code> — "
                f"{wins} vitórias | 🔥 {best_streak} | 🎯 {best_score_text}"
            )
        else:
            avg_attempts = float(row.get("avg_attempts") or 0)
            avg_text = f"{avg_attempts:.2f}" if avg_attempts else "-"
            lines.append(
                f"{icon} <code>{user_id}</code> — "
                f"{wins} vitórias | média {avg_text}"
            )

    return "\n".join(lines)


def _start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Iniciar Desafio", callback_data="termo_start")],
        [InlineKeyboardButton("📊 Estatísticas", callback_data="termo_stats")],
        [InlineKeyboardButton("🏆 Ranking", callback_data="termo_ranking")],
    ])


def _post_buttons(training: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📊 Estatísticas", callback_data="termo_stats")],
        [InlineKeyboardButton("🏆 Ranking", callback_data="termo_ranking")],
    ]
    if training:
        rows.append([InlineKeyboardButton("🧪 Jogar treino novamente", callback_data="termo_train_start")])
    return InlineKeyboardMarkup(rows)


def _intro_text() -> str:
    return (
        "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b> relacionada ao mundo dos animes.\n\n"
        "Você possui:\n\n"
        "🎯 6 tentativas\n"
        "⏱ 5 minutos para resolver\n"
        "🎁 Recompensa ao acertar\n\n"
        "🪙 Coins variáveis por desempenho\n"
        f"⭐ +{XP_REWARD} XP\n\n"
        "Como funciona:\n\n"
        "🟩 Letra correta na posição correta\n"
        "🟨 Letra existe mas posição errada\n"
        "⬛ Letra não existe\n\n"
        "A palavra muda todos os dias às 00:00.\n\n"
        "🔥 Mantenha sua sequência diária para ganhar bônus!"
    )


def _board_text(game: Dict[str, Any]) -> str:
    guesses = game["guesses"]
    attempts = len(guesses)
    seconds_left = _seconds_left(int(game["start_time"]))

    parts = [
        "🎌 <b>TERMO ANIME</b>",
        "",
        _history_text(guesses),
        "",
        f"Tentativas: <b>{attempts}/6</b>",
        f"Tempo restante: <b>{_format_mmss(seconds_left)}</b>",
        "",
        "⌨️ <b>Teclado</b>",
        _keyboard_visual(guesses),
    ]

    used = _used_letters(guesses)
    if used:
        parts.extend(["", "🔤 <b>Letras usadas:</b>", used])

    if game.get("mode") == "train":
        parts.extend(["", "🧪 <b>Modo treino</b>"])

    return "\n".join(parts)


def _timeout_text(game: Dict[str, Any]) -> str:
    return (
        "⏱ <b>Tempo esgotado!</b>\n\n"
        f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
        f"Categoria: <b>{game['category']}</b>\n"
        f"Origem: <b>{game['source']}</b>\n\n"
        f"📅 Próxima palavra em <b>{_next_reset_text()}</b>."
    )


def _lose_text(game: Dict[str, Any], streak_lost: bool) -> str:
    streak_text = "\n❌ <b>Sequência perdida!</b>" if streak_lost else ""

    return (
        "❌ <b>Fim de jogo</b>\n\n"
        f"{_history_text(game['guesses'])}\n\n"
        f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
        f"Categoria: <b>{game['category']}</b>\n"
        f"Origem: <b>{game['source']}</b>"
        f"{streak_text}\n\n"
        f"📅 Próxima palavra em <b>{_next_reset_text()}</b>."
    )


def _win_text(
    game: Dict[str, Any],
    current_streak: int,
    reward_coins: int,
    bonus_coins: int,
    training: bool = False,
) -> str:
    share = _share_text(
        guesses=game["guesses"],
        attempts=len(game["guesses"]),
        win=True,
        streak=current_streak,
        training=training,
    )

    if training:
        return (
            "🎉 <b>Você acertou no modo treino!</b>\n\n"
            f"{_history_text(game['guesses'])}\n\n"
            f"Palavra: <b>{game['word'].upper()}</b>\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>\n\n"
            f"📤 <b>Compartilhar resultado:</b>\n"
            f"<code>{share}</code>"
        )

    bonus_text = f"\n🎁 Bônus de streak: <b>+{bonus_coins} Coins</b>" if bonus_coins > 0 else ""

    return (
        "🎉 <b>Você acertou!</b>\n\n"
        f"{_history_text(game['guesses'])}\n\n"
        f"Palavra: <b>{game['word'].upper()}</b>\n"
        f"Categoria: <b>{game['category']}</b>\n"
        f"Origem: <b>{game['source']}</b>\n\n"
        f"🪙 +<b>{reward_coins}</b> Coins\n"
        f"⭐ +<b>{XP_REWARD}</b> XP"
        f"{bonus_text}\n\n"
        f"🔥 Sequência atual: <b>{current_streak} dias</b>\n\n"
        f"📤 <b>Compartilhar resultado:</b>\n"
        f"<code>{share}</code>"
    )


async def _start_daily_game(update: Update, from_callback: bool = False) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    create_or_get_user(user_id)
    ensure_termo_stats_row(user_id)

    today = _today()
    existing_daily = get_termo_daily_game(user_id, today)

    if existing_daily:
        status = str(existing_daily.get("status") or "")
        if status == "playing":
            game = _cache_game_from_row(existing_daily)
            text = _board_text(game)
            if from_callback and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode="HTML")
            else:
                await update.effective_message.reply_text(text, parse_mode="HTML")
            return

        text = (
            "❌ Você já jogou o desafio de hoje.\n\n"
            f"📅 Próxima palavra em <b>{_next_reset_text()}</b>."
        )
        if from_callback and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        else:
            await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    word_data = _pick_daily_word(user_id)

    create_termo_game(
        user_id=user_id,
        game_date=today,
        word=word_data["word"],
        category=word_data["category"],
        source=word_data["source"],
        start_time=int(time.time()),
        mode="daily",
    )

    mark_termo_word_used(user_id, word_data["word"])

    game = {
        "user_id": user_id,
        "date": today,
        "word": word_data["word"],
        "category": word_data["category"],
        "source": word_data["source"],
        "attempts": 0,
        "guesses": [],
        "used_letters": "",
        "status": "playing",
        "mode": "daily",
        "start_time": int(time.time()),
    }
    ACTIVE_GAMES[user_id] = game

    text = (
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras."
    )

    if from_callback and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML")


async def _start_training_game(update: Update, from_callback: bool = False) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    if not _is_admin(user_id):
        text = "❌ Apenas admins podem usar o modo treino."
        if from_callback and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return

    word_data = _pick_training_word()

    ACTIVE_GAMES[user_id] = {
        "user_id": user_id,
        "date": _today(),
        "word": word_data["word"],
        "category": word_data["category"],
        "source": word_data["source"],
        "attempts": 0,
        "guesses": [],
        "used_letters": "",
        "status": "playing",
        "mode": "train",
        "start_time": int(time.time()),
    }

    text = (
        "🧪 <b>TERMO TREINO</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras."
    )

    if from_callback and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML")


async def termo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    text = _normalize_text(update.message.text)
    user_id = int(update.effective_user.id)

    if text == "termo":
        game = _get_active_game(user_id)
        if game:
            await update.message.reply_text(_board_text(game), parse_mode="HTML")
            return

        await update.message.reply_text(
            _intro_text(),
            parse_mode="HTML",
            reply_markup=_start_buttons(),
        )
        return

    if text == "termo stats":
        await update.message.reply_text(_stats_text(user_id), parse_mode="HTML")
        return

    if text == "termo ranking":
        await update.message.reply_text(
            _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
            parse_mode="HTML",
        )
        return

    if text == "termo ranking semana":
        await update.message.reply_text(
            _ranking_text(get_termo_period_ranking(7, 10), "Ranking Termo — Semana"),
            parse_mode="HTML",
        )
        return

    if text == "termo ranking mes":
        await update.message.reply_text(
            _ranking_text(get_termo_period_ranking(30, 10), "Ranking Termo — Mês"),
            parse_mode="HTML",
        )
        return

    if text == "termo treino":
        await _start_training_game(update, from_callback=False)
        return

    if text == "termo treino stats":
        if not _is_admin(user_id):
            await update.message.reply_text("❌ Apenas admins podem usar isso.")
            return

        game = ACTIVE_GAMES.get(user_id)
        if not game or game.get("mode") != "train":
            await update.message.reply_text("❌ Nenhum treino ativo.")
            return

        await update.message.reply_text(_board_text(game), parse_mode="HTML")
        return

    if text == "termo treino stop":
        if not _is_admin(user_id):
            await update.message.reply_text("❌ Apenas admins podem usar isso.")
            return

        game = ACTIVE_GAMES.get(user_id)
        if game and game.get("mode") == "train":
            ACTIVE_GAMES.pop(user_id, None)
            await update.message.reply_text("🧪 Treino encerrado.")
        else:
            await update.message.reply_text("❌ Nenhum treino ativo.")
        return


async def termo_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = str(query.data or "")
    await query.answer()

    if data == "termo_start":
        await _start_daily_game(update, from_callback=True)
        return

    if data == "termo_stats":
        await query.edit_message_text(
            _stats_text(int(query.from_user.id)),
            parse_mode="HTML",
            reply_markup=_post_buttons(training=False),
        )
        return

    if data == "termo_ranking":
        await query.edit_message_text(
            _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
            parse_mode="HTML",
            reply_markup=_post_buttons(training=False),
        )
        return

    if data == "termo_train_start":
        await _start_training_game(update, from_callback=True)
        return


async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    guess = _normalize_text(update.message.text)
    user_id = int(update.effective_user.id)

    if guess.startswith("termo"):
        return

    if len(guess) != WORD_LENGTH:
        return

    if not _is_valid_word_format(guess):
        await update.message.reply_text("❌ Envie apenas uma palavra válida de 6 letras.")
        return

    _load_words()
    if guess not in VALID_WORDS_SET:
        await update.message.reply_text("❌ Palavra inválida.")
        return

    game = _get_active_game(user_id)
    if not game:
        return

    if not _anti_flood_ok(user_id):
        return

    if _seconds_left(int(game["start_time"])) <= 0:
        training = game.get("mode") == "train"
        if not training:
            record_termo_result(user_id, win=False, attempts=len(game["guesses"]))
        _finish_current_game(game, "timeout", reward_coins=0, reward_xp=0)

        await update.message.reply_text(
            _timeout_text(game),
            parse_mode="HTML",
            reply_markup=_post_buttons(training=training),
        )
        return

    if guess in {str(g.get("guess", "")).lower() for g in game["guesses"]}:
        await update.message.reply_text("❌ Palavra já usada.")
        return

    result = _evaluate_guess(game["word"], guess)

    game["guesses"].append({
        "guess": guess,
        "result": result,
        "ts": int(time.time()),
    })
    _save_progress(game)

    if guess == game["word"]:
        training = game.get("mode") == "train"
        reward_coins = 0
        bonus_coins = 0
        current_streak = 0

        if not training:
            record_termo_result(user_id, win=True, attempts=len(game["guesses"]))
            stats = get_termo_stats(user_id) or {}
            current_streak = int(stats.get("current_streak") or 0)

            reward_coins = _daily_coins_for_attempt(len(game["guesses"]))
            bonus_coins = _streak_bonus(current_streak)

            add_user_coins(user_id, reward_coins + bonus_coins)
            add_progress_xp(user_id, XP_REWARD)

        _finish_current_game(
            game,
            "win",
            reward_coins=reward_coins + bonus_coins,
            reward_xp=0 if training else XP_REWARD,
        )

        await update.message.reply_text(
            _win_text(
                game=game,
                current_streak=current_streak,
                reward_coins=reward_coins,
                bonus_coins=bonus_coins,
                training=training,
            ),
            parse_mode="HTML",
            reply_markup=_post_buttons(training=training),
        )
        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:
        training = game.get("mode") == "train"

        old_stats = get_termo_stats(user_id) or {}
        old_streak = int(old_stats.get("current_streak") or 0)

        if not training:
            record_termo_result(user_id, win=False, attempts=len(game["guesses"]))

        _finish_current_game(game, "lose", reward_coins=0, reward_xp=0)

        await update.message.reply_text(
            _lose_text(game, streak_lost=(old_streak > 0 and not training)),
            parse_mode="HTML",
            reply_markup=_post_buttons(training=training),
        )
        return

    await update.message.reply_text(_board_text(game), parse_mode="HTML")
