# commands/termo.py

import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import (
    _run,
    add_progress_xp,
    create_or_get_user,
    create_termo_game,
    ensure_termo_stats_row,
    finish_termo_game,
    get_termo_active_game,
    get_termo_daily_game,
    get_termo_global_ranking,
    get_termo_stats,
    get_termo_user_rank,
    has_user_used_termo_word,
    mark_termo_word_used,
    record_termo_result,
    update_termo_game_progress,
)

# =========================================================
# CONFIG
# =========================================================

WORDS_FILE = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json")
TIME_LIMIT_SECONDS = 5 * 60
MAX_ATTEMPTS = 6
WORD_LENGTH = 6
ANTI_FLOOD_SECONDS = 2.0

COIN_REWARD = 2
XP_REWARD = 10

# IDs de admins separados por vírgula no env:
# ADMIN_IDS=123,456,789
ADMIN_IDS: Set[int] = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# cache em memória
ACTIVE_GAMES: Dict[int, Dict[str, Any]] = {}
LAST_INPUT_AT: Dict[int, float] = {}

# cache do arquivo de palavras
WORDS_CACHE: List[Dict[str, str]] = []
WORDS_SET: Set[str] = set()


# =========================================================
# BOOT / HELPERS GERAIS
# =========================================================

def _ensure_users_coins_column() -> None:
    """
    Garante compatibilidade com recompensa de coins,
    mesmo se a tabela users antiga ainda não tiver a coluna.
    """
    _run("""
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS coins BIGINT NOT NULL DEFAULT 0
    """)


def _load_words() -> List[Dict[str, str]]:
    global WORDS_CACHE, WORDS_SET

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
        category = str(item.get("category", "")).strip()
        source = str(item.get("source", "")).strip()

        if not _is_valid_word(word):
            continue

        if word in seen:
            continue

        seen.add(word)
        clean.append({
            "word": word,
            "category": category or "Desconhecido",
            "source": source or "Anime",
        })

    WORDS_CACHE = clean
    WORDS_SET = {w["word"] for w in clean}
    return WORDS_CACHE


def _is_valid_word(word: str) -> bool:
    if not word:
        return False

    word = word.strip().lower()

    if len(word) != WORD_LENGTH:
        return False

    # aceita só letras simples; remove qualquer coisa estranha
    if not re.fullmatch(r"[a-záàâãéèêíìîóòôõúùûç]+", word):
        return False

    return True


def _normalize_guess(text: str) -> str:
    return (text or "").strip().lower()


def _anti_flood_ok(user_id: int) -> bool:
    now = time.time()
    last = LAST_INPUT_AT.get(int(user_id), 0.0)
    if now - last < ANTI_FLOOD_SECONDS:
        return False
    LAST_INPUT_AT[int(user_id)] = now
    return True


def _today() -> date:
    return date.today()


def _seconds_left(start_time: int) -> int:
    elapsed = int(time.time()) - int(start_time)
    return max(TIME_LIMIT_SECONDS - elapsed, 0)


def _format_seconds(seconds: int) -> str:
    minutes = seconds // 60
    sec = seconds % 60
    return f"{minutes}:{sec:02d}"


def _is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _safe_username(user) -> str:
    if not user:
        return ""
    if getattr(user, "username", None):
        return f"@{user.username}"
    if getattr(user, "first_name", None):
        return user.first_name
    return str(getattr(user, "id", "Usuário"))


# =========================================================
# ESCOLHA DE PALAVRA
# =========================================================

def _pick_daily_word_for_user(user_id: int) -> Dict[str, str]:
    words = _load_words()
    if not words:
        raise RuntimeError("Arquivo de palavras vazio ou inválido.")

    unused = [w for w in words if not has_user_used_termo_word(int(user_id), w["word"])]
    pool = unused if unused else words

    # seed estável por usuário e dia
    seed = f"{int(user_id)}:{_today().isoformat()}"
    rng = random.Random(seed)

    choice = rng.choice(pool)
    return choice


def _pick_training_word() -> Dict[str, str]:
    words = _load_words()
    if not words:
        raise RuntimeError("Arquivo de palavras vazio ou inválido.")
    return random.choice(words)


# =========================================================
# WORDLE LOGIC
# =========================================================

def _evaluate_guess(secret: str, guess: str) -> str:
    """
    Avaliação estilo Wordle:
    🟩 letra certa no lugar certo
    🟨 letra existe mas em outra posição
    ⬛ letra não existe
    """
    secret = secret.lower()
    guess = guess.lower()

    result = ["⬛"] * WORD_LENGTH
    remaining: Dict[str, int] = {}

    # primeira passada: verdes
    for i in range(WORD_LENGTH):
        if guess[i] == secret[i]:
            result[i] = "🟩"
        else:
            remaining[secret[i]] = remaining.get(secret[i], 0) + 1

    # segunda passada: amarelos
    for i in range(WORD_LENGTH):
        if result[i] == "🟩":
            continue
        ch = guess[i]
        if remaining.get(ch, 0) > 0:
            result[i] = "🟨"
            remaining[ch] -= 1

    return "".join(result)


def _collect_used_letters(guesses: List[Dict[str, Any]]) -> str:
    used: List[str] = []
    seen: Set[str] = set()

    for item in guesses:
        word = str(item.get("guess", "")).upper()
        for ch in word:
            if ch.isalpha() and ch not in seen:
                seen.add(ch)
                used.append(ch)

    return " ".join(used)


def _build_history_lines(guesses: List[Dict[str, Any]]) -> str:
    if not guesses:
        return ""

    lines: List[str] = []
    for item in guesses:
        g = str(item.get("guess", "")).upper()
        r = str(item.get("result", ""))
        lines.append(f"{g}\n{r}")

    return "\n\n".join(lines)


def _build_share_text(
    guesses: List[Dict[str, Any]],
    attempts: int,
    win: bool,
    streak: int,
    training: bool = False,
) -> str:
    rows = [str(item.get("result", "")) for item in guesses]
    grid = "\n".join(rows) if rows else "⬛⬛⬛⬛⬛⬛"

    mode_suffix = " (Treino)" if training else ""
    score = f"{attempts}/6" if win else "X/6"

    return (
        f"🎌 TERMO ANIME — SourceBaltigo{mode_suffix}\n\n"
        f"{grid}\n\n"
        f"{score}\n"
        f"🔥 Streak: {streak}"
    )


def _next_daily_reset_text() -> str:
    now = datetime.now()
    tomorrow = datetime.combine((now + timedelta(days=1)).date(), datetime.min.time())
    delta = tomorrow - now
    total = int(delta.total_seconds())
    hours = total // 3600
    minutes = (total % 3600) // 60
    return f"{hours}h {minutes}m"


# =========================================================
# DB / CACHE SYNC
# =========================================================

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
        "category": str(row.get("category", "") or "Desconhecido"),
        "source": str(row.get("source", "") or "Anime"),
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

    cached = ACTIVE_GAMES.get(user_id)
    if cached and cached.get("status") == "playing":
        return cached

    row = get_termo_active_game(user_id)
    if not row:
        ACTIVE_GAMES.pop(user_id, None)
        return None

    return _cache_game_from_row(row)


def _store_progress(game: Dict[str, Any]) -> None:
    game["attempts"] = len(game["guesses"])
    game["used_letters"] = _collect_used_letters(game["guesses"])

    update_termo_game_progress(
        user_id=int(game["user_id"]),
        attempts=int(game["attempts"]),
        guesses_json=_json_dumps(game["guesses"]),
        used_letters=str(game["used_letters"]),
    )

    ACTIVE_GAMES[int(game["user_id"])] = game


def _finish_game(game: Dict[str, Any], status: str) -> None:
    game["status"] = status
    game["attempts"] = len(game["guesses"])
    game["used_letters"] = _collect_used_letters(game["guesses"])

    finish_termo_game(
        user_id=int(game["user_id"]),
        status=status,
        attempts=int(game["attempts"]),
        guesses_json=_json_dumps(game["guesses"]),
        used_letters=str(game["used_letters"]),
    )

    ACTIVE_GAMES.pop(int(game["user_id"]), None)


# =========================================================
# STATS / REWARD
# =========================================================

def _reward_user(user_id: int, coins: int, xp: int) -> None:
    _ensure_users_coins_column()

    _run(
        """
        UPDATE users
        SET coins = COALESCE(coins, 0) + %s
        WHERE user_id = %s
        """,
        (int(coins), int(user_id)),
    )

    add_progress_xp(int(user_id), int(xp))


def _streak_bonus(current_streak: int) -> int:
    if current_streak > 0 and current_streak % 30 == 0:
        return 50
    if current_streak > 0 and current_streak % 7 == 0:
        return 10
    if current_streak > 0 and current_streak % 3 == 0:
        return 5
    return 0


def _win_rate(stats: Dict[str, Any]) -> int:
    games = int(stats.get("games_played") or 0)
    wins = int(stats.get("wins") or 0)
    if games <= 0:
        return 0
    return int(round((wins / games) * 100))


def _build_stats_text(user_id: int) -> str:
    ensure_termo_stats_row(int(user_id))
    stats = get_termo_stats(int(user_id)) or {}
    rank = get_termo_user_rank(int(user_id))

    games_played = int(stats.get("games_played") or 0)
    wins = int(stats.get("wins") or 0)
    losses = int(stats.get("losses") or 0)
    current_streak = int(stats.get("current_streak") or 0)
    best_streak = int(stats.get("best_streak") or 0)
    best_score = int(stats.get("best_score") or 0)
    win_rate = _win_rate(stats)

    best_score_text = str(best_score) if best_score > 0 else "-"

    return (
        "📊 <b>Estatísticas Termo</b>\n\n"
        f"🎮 Jogos: <b>{games_played}</b>\n"
        f"✅ Vitórias: <b>{wins}</b>\n"
        f"❌ Derrotas: <b>{losses}</b>\n"
        f"📈 Taxa de vitória: <b>{win_rate}%</b>\n\n"
        f"🔥 Streak atual: <b>{current_streak}</b>\n"
        f"🏆 Melhor streak: <b>{best_streak}</b>\n"
        f"🎯 Melhor score: <b>{best_score_text}</b>\n"
        f"🌍 Ranking global: <b>{rank if rank > 0 else '-'}</b>"
    )


def _build_ranking_text(limit: int = 10) -> str:
    rows = get_termo_global_ranking(limit=limit)

    if not rows:
        return "🏆 <b>Ranking Termo</b>\n\nAinda não há partidas registradas."

    lines = ["🏆 <b>Ranking Termo Anime</b>\n"]

    medals = ["1️⃣", "2️⃣", "3️⃣"]
    for idx, row in enumerate(rows, start=1):
        icon = medals[idx - 1] if idx <= 3 else f"{idx}."
        user_id = int(row.get("user_id") or 0)
        wins = int(row.get("wins") or 0)
        best_streak = int(row.get("best_streak") or 0)
        best_score = int(row.get("best_score") or 0)
        best_score_text = best_score if best_score > 0 else "-"
        lines.append(
            f"{icon} <code>{user_id}</code> — "
            f"{wins} vitórias | 🔥 {best_streak} | 🎯 {best_score_text}"
        )

    return "\n".join(lines)


# =========================================================
# UI
# =========================================================

def _start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Iniciar Desafio", callback_data="termo_start")],
        [InlineKeyboardButton("📊 Estatísticas", callback_data="termo_stats")],
        [InlineKeyboardButton("🏆 Ranking", callback_data="termo_ranking")],
    ])


def _post_game_buttons(training: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 Estatísticas", callback_data="termo_stats")],
        [InlineKeyboardButton("🏆 Ranking", callback_data="termo_ranking")],
    ]

    if training:
        buttons.append([InlineKeyboardButton("🧪 Jogar treino novamente", callback_data="termo_train_start")])

    return InlineKeyboardMarkup(buttons)


def _build_board_text(game: Dict[str, Any]) -> str:
    seconds_left = _seconds_left(int(game["start_time"]))
    history = _build_history_lines(game["guesses"])
    used_letters = game.get("used_letters") or _collect_used_letters(game["guesses"])
    attempts = len(game["guesses"])

    parts = [
        "🎌 <b>TERMO ANIME</b>",
        "",
        "⬛⬛⬛⬛⬛⬛" if not history else history,
        "",
        f"Tentativas: <b>{attempts}/6</b>",
        f"Tempo restante: <b>{_format_seconds(seconds_left)}</b>",
    ]

    if used_letters:
        parts.extend([
            "",
            "🔤 <b>Letras usadas:</b>",
            used_letters,
        ])

    if game.get("mode") == "train":
        parts.extend([
            "",
            "🧪 <b>Modo treino</b>",
        ])

    return "\n".join(parts)


def _build_intro_text() -> str:
    return (
        "🎌 <b>TERMO ANIME — SourceBaltigo</b>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b> relacionada ao mundo dos animes.\n\n"
        "Você possui:\n\n"
        "🎯 6 tentativas\n"
        "⏱ 5 minutos para resolver\n"
        "🎁 Recompensa ao acertar\n\n"
        f"🪙 +{COIN_REWARD} Coins\n"
        f"⭐ +{XP_REWARD} XP\n\n"
        "Como funciona:\n\n"
        "🟩 Letra correta na posição correta\n"
        "🟨 Letra existe mas posição errada\n"
        "⬛ Letra não existe\n\n"
        "A palavra muda todos os dias às 00:00.\n\n"
        "🔥 Mantenha sua sequência diária para ganhar bônus!"
    )


def _build_timeout_text(game: Dict[str, Any]) -> str:
    return (
        "⏱ <b>Tempo esgotado!</b>\n\n"
        f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
        f"Categoria: <b>{game['category']}</b>\n"
        f"Origem: <b>{game['source']}</b>\n\n"
        f"Próxima palavra em <b>{_next_daily_reset_text()}</b>."
    )


def _build_lose_text(game: Dict[str, Any], streak_lost: bool) -> str:
    history = _build_history_lines(game["guesses"])
    streak_text = "\n❌ <b>Sequência perdida!</b>\n" if streak_lost else "\n"

    return (
        "❌ <b>Fim de jogo</b>\n\n"
        f"{history}\n\n"
        f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
        f"Categoria: <b>{game['category']}</b>\n"
        f"Origem: <b>{game['source']}</b>"
        f"{streak_text}\n"
        f"📅 Próxima palavra em <b>{_next_daily_reset_text()}</b>."
    )


def _build_win_text(
    game: Dict[str, Any],
    current_streak: int,
    bonus_coins: int,
    share_text: str,
    training: bool = False,
) -> str:
    history = _build_history_lines(game["guesses"])
    attempts = len(game["guesses"])

    if training:
        return (
            "🎉 <b>Você acertou no modo treino!</b>\n\n"
            f"{history}\n\n"
            f"Palavra: <b>{game['word'].upper()}</b>\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>\n\n"
            f"🎯 Tentativas: <b>{attempts}/6</b>\n\n"
            f"📤 <b>Compartilhar resultado:</b>\n"
            f"<code>{share_text}</code>"
        )

    bonus_text = f"\n🎁 Bônus de streak: <b>+{bonus_coins} Coins</b>" if bonus_coins > 0 else ""

    return (
        "🎉 <b>Você acertou!</b>\n\n"
        f"{history}\n\n"
        f"Palavra: <b>{game['word'].upper()}</b>\n"
        f"Categoria: <b>{game['category']}</b>\n"
        f"Origem: <b>{game['source']}</b>\n\n"
        f"🪙 +<b>{COIN_REWARD}</b> Coins\n"
        f"⭐ +<b>{XP_REWARD}</b> XP"
        f"{bonus_text}\n\n"
        f"🔥 Sequência atual: <b>{current_streak} dias</b>\n"
        f"🎯 Tentativas: <b>{attempts}/6</b>\n\n"
        f"📤 <b>Compartilhar resultado:</b>\n"
        f"<code>{share_text}</code>"
    )


# =========================================================
# START GAME
# =========================================================

async def _start_daily_game(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback: bool = False) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    create_or_get_user(user_id)
    ensure_termo_stats_row(user_id)
    _ensure_users_coins_column()

    today = _today()
    existing_daily = get_termo_daily_game(user_id, today)
    if existing_daily:
        status = str(existing_daily.get("status") or "")

        if status == "playing":
            game = _cache_game_from_row(existing_daily)
            text = _build_board_text(game)
            if from_callback and update.callback_query:
                await update.callback_query.edit_message_text(
                    text,
                    parse_mode="HTML",
                )
            else:
                await update.effective_message.reply_text(text, parse_mode="HTML")
            return

        await (update.callback_query.edit_message_text if from_callback and update.callback_query else update.effective_message.reply_text)(
            "❌ Você já jogou o desafio de hoje.\n\n"
            f"📅 Próxima palavra em <b>{_next_daily_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    word_data = _pick_daily_word_for_user(user_id)

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


async def _start_training_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)

    if not _is_admin(user_id):
        await update.effective_message.reply_text("❌ Apenas admins podem usar o modo treino.")
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

    await update.effective_message.reply_text(
        "🧪 <b>TERMO TREINO</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras.",
        parse_mode="HTML",
    )


# =========================================================
# PUBLIC HANDLERS
# =========================================================

async def termo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ativado por mensagem sem barra:
    - termo
    - termo treino
    - termo stats
    - termo ranking
    """
    if not update.message or not update.message.text:
        return

    text = _normalize_guess(update.message.text)

    if text == "termo":
        await update.message.reply_text(
            _build_intro_text(),
            parse_mode="HTML",
            reply_markup=_start_buttons(),
        )
        return

    if text == "termo treino":
        await _start_training_game(update, context)
        return

    if text == "termo stats":
        stats_text = _build_stats_text(int(update.effective_user.id))
        await update.message.reply_text(stats_text, parse_mode="HTML")
        return

    if text == "termo ranking":
        ranking_text = _build_ranking_text()
        await update.message.reply_text(ranking_text, parse_mode="HTML")
        return


async def termo_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = str(query.data or "")
    await query.answer()

    if data == "termo_start":
        await _start_daily_game(update, context, from_callback=True)
        return

    if data == "termo_stats":
        await query.edit_message_text(
            _build_stats_text(int(query.from_user.id)),
            parse_mode="HTML",
            reply_markup=_post_game_buttons(training=False),
        )
        return

    if data == "termo_ranking":
        await query.edit_message_text(
            _build_ranking_text(),
            parse_mode="HTML",
            reply_markup=_post_game_buttons(training=False),
        )
        return

    if data == "termo_train_start":
        user_id = int(query.from_user.id)
        if not _is_admin(user_id):
            await query.edit_message_text("❌ Apenas admins podem usar o modo treino.")
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

        await query.edit_message_text(
            "🧪 <b>TERMO TREINO</b>\n\n"
            "⬛⬛⬛⬛⬛⬛\n\n"
            "Tentativas: <b>0/6</b>\n"
            "Tempo restante: <b>5:00</b>\n\n"
            "Digite uma palavra de 6 letras.",
            parse_mode="HTML",
        )
        return


async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    guess = _normalize_guess(update.message.text)
    user_id = int(update.effective_user.id)

    # ignora mensagens que não têm 6 letras ou são mensagens de controle "termo ..."
    if guess.startswith("termo"):
        return

    if len(guess) != WORD_LENGTH:
        return

    if not _is_valid_word(guess):
        await update.message.reply_text("❌ Envie apenas uma palavra válida de 6 letras.")
        return

    game = _get_active_game(user_id)
    if not game:
        return

    if not _anti_flood_ok(user_id):
        return

    seconds_left = _seconds_left(int(game["start_time"]))
    if seconds_left <= 0:
        training = game.get("mode") == "train"

        if not training:
            record_termo_result(user_id, win=False, attempts=len(game["guesses"]))
        _finish_game(game, "timeout")

        await update.message.reply_text(
            _build_timeout_text(game),
            parse_mode="HTML",
            reply_markup=_post_game_buttons(training=training),
        )
        return

    if len(game["guesses"]) >= MAX_ATTEMPTS:
        return

    result = _evaluate_guess(game["word"], guess)

    game["guesses"].append({
        "guess": guess,
        "result": result,
        "ts": int(time.time()),
    })

    _store_progress(game)

    # vitória
    if guess == game["word"]:
        training = game.get("mode") == "train"

        current_streak = 0
        bonus_coins = 0

        if not training:
            record_termo_result(user_id, win=True, attempts=len(game["guesses"]))
            stats = get_termo_stats(user_id) or {}
            current_streak = int(stats.get("current_streak") or 0)

            bonus_coins = _streak_bonus(current_streak)
            _reward_user(user_id, COIN_REWARD + bonus_coins, XP_REWARD)
        else:
            stats = get_termo_stats(user_id) or {}
            current_streak = int(stats.get("current_streak") or 0)

        share_text = _build_share_text(
            guesses=game["guesses"],
            attempts=len(game["guesses"]),
            win=True,
            streak=current_streak,
            training=training,
        )

        _finish_game(game, "win")

        await update.message.reply_text(
            _build_win_text(
                game=game,
                current_streak=current_streak,
                bonus_coins=bonus_coins,
                share_text=share_text,
                training=training,
            ),
            parse_mode="HTML",
            reply_markup=_post_game_buttons(training=training),
        )
        return

    # derrota por tentativas
    if len(game["guesses"]) >= MAX_ATTEMPTS:
        training = game.get("mode") == "train"

        old_stats = get_termo_stats(user_id) or {}
        old_streak = int(old_stats.get("current_streak") or 0)

        if not training:
            record_termo_result(user_id, win=False, attempts=len(game["guesses"]))

        _finish_game(game, "lose")

        await update.message.reply_text(
            _build_lose_text(game, streak_lost=(old_streak > 0 and not training)),
            parse_mode="HTML",
            reply_markup=_post_game_buttons(training=training),
        )
        return

    # partida continua
    await update.message.reply_text(
        _build_board_text(game),
        parse_mode="HTML",
    )
