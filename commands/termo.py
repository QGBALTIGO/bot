"""
commands/termo.py  —  TERMO ANIME · SourceBaltigo
Versão 2.0  |  Refatoração completa
"""

from __future__ import annotations

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


# ─────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────

WORDS_FILE      = os.getenv("TERMO_WORDS_FILE", "data/anime_words_365.json")
SP_TZ           = ZoneInfo("America/Sao_Paulo")
TIME_LIMIT_SECS = 300          # 5 minutos
MAX_ATTEMPTS    = 6
WORD_LENGTH     = 6
ANTI_FLOOD_SECS = 1.5
XP_REWARD       = 10
HINT_COST_COINS = 5            # custo para pedir dica

ADMIN_IDS: Set[int] = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

# ─────────────────────────────────────────────
#  Estado em memória
# ─────────────────────────────────────────────

ACTIVE_GAMES: Dict[int, Dict[str, Any]] = {}
LAST_GUESS_AT:  Dict[int, float]        = {}
WORDS_CACHE:    List[Dict[str, Any]]    = []
VALID_WORDS:    Set[str]                = set()
_WORD_INDEX:    Dict[str, Dict[str, Any]] = {}   # word → entry (para dicas rápidas)


# ═════════════════════════════════════════════
#  PALAVRAS E TEMPO
# ═════════════════════════════════════════════

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
    delta   = tomorrow - now
    total   = int(delta.total_seconds())
    hours   = total // 3600
    minutes = (total % 3600) // 60
    return f"{hours}h {minutes}min"

def _valid_format(word: str) -> bool:
    return bool(re.fullmatch(r"[a-záàâãéèêíìîóòôõúùûç]{6}", (word or "").strip().lower()))

def _normalize(text: str) -> str:
    return (text or "").strip().lower()

def _load_words() -> List[Dict[str, Any]]:
    global WORDS_CACHE, VALID_WORDS, _WORD_INDEX
    if WORDS_CACHE:
        return WORDS_CACHE

    with open(WORDS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    cleaned: List[Dict[str, Any]] = []
    seen:    Set[str]             = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        word     = str(item.get("word", "")).strip().lower()
        category = str(item.get("category", "")).strip() or "Desconhecido"
        source   = str(item.get("source",   "")).strip() or "Anime"
        difficulty = int(item.get("difficulty", 1))
        hint     = str(item.get("hint", "")).strip()

        if not _valid_format(word) or word in seen:
            continue
        seen.add(word)
        entry = {"word": word, "category": category, "source": source,
                 "difficulty": difficulty, "hint": hint}
        cleaned.append(entry)
        _WORD_INDEX[word] = entry

    WORDS_CACHE = cleaned
    VALID_WORDS = {x["word"] for x in cleaned}
    return WORDS_CACHE


# ─────────────────────────────────────────────
#  Helpers de administração / anti-flood
# ─────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS

def _anti_flood_ok(user_id: int) -> bool:
    now  = time.time()
    last = LAST_GUESS_AT.get(int(user_id), 0.0)
    if now - last < ANTI_FLOOD_SECS:
        return False
    LAST_GUESS_AT[int(user_id)] = now
    return True

def _seconds_left(start_time: int) -> int:
    return max(TIME_LIMIT_SECS - (int(time.time()) - int(start_time)), 0)

def _fmt_mmss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


# ═════════════════════════════════════════════
#  GATEKEEPER
# ═════════════════════════════════════════════

def _touch_identity(update: Update) -> None:
    user = update.effective_user
    if not user:
        return
    create_or_get_user(int(user.id))
    touch_user_identity(
        int(user.id),
        getattr(user, "username", "") or "",
        " ".join(p for p in [
            getattr(user, "first_name", "") or "",
            getattr(user, "last_name",  "") or "",
        ] if p).strip(),
    )

async def _gate_ok(update: Update) -> bool:
    user = update.effective_user
    msg  = update.effective_message
    if not user or not msg:
        return False
    _touch_identity(update)
    if has_accepted_terms(int(user.id), TERMS_VERSION):
        return True
    await msg.reply_text(
        "⛩️ Para jogar o Termo Anime você precisa aceitar os termos primeiro.\n\n"
        "Use /start e conclua o aceite."
    )
    return False


# ═════════════════════════════════════════════
#  LÓGICA DO JOGO
# ═════════════════════════════════════════════

def _daily_coins(attempts: int) -> int:
    """Recompensa em coins por número de tentativas."""
    return max(12 - (attempts - 1) * 2, 2)
    # 1→12, 2→10, 3→8, 4→6, 5→4, 6→2

def _streak_bonus(streak: int) -> int:
    if streak > 0 and streak % 30 == 0: return 50
    if streak > 0 and streak % 7  == 0: return 15
    if streak > 0 and streak % 3  == 0: return 5
    return 0

def _pick_daily_word(user_id: int) -> Dict[str, Any]:
    words     = _load_words()
    available = [w for w in words if not has_user_used_termo_word(user_id, w["word"])]
    pool      = available if available else words
    # seed determinístico por usuário+dia garante palavra consistente mesmo após restart
    rng = random.Random(f"{user_id}:{_sp_today().isoformat()}")
    return rng.choice(pool)

def _pick_train_word() -> Dict[str, Any]:
    return random.choice(_load_words())

def _evaluate(secret: str, guess: str) -> str:
    """Retorna string de emojis: 🟩🟨⬛"""
    result    = ["⬛"] * WORD_LENGTH
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

def _letter_map(guesses: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Retorna mapa letra → melhor status ('🟩' > '🟨' > '⬛')
    para o teclado visual de letras usadas.
    """
    PRIORITY = {"🟩": 3, "🟨": 2, "⬛": 1}
    mp: Dict[str, str] = {}
    for item in guesses:
        guess  = str(item.get("guess",  ""))
        result = str(item.get("result", ""))
        # result é string de emojis de 3 bytes cada
        emojis = [result[i:i+1] for i in range(len(result))]
        # cada emoji é um caractere unicode; split seguro:
        emoji_list = []
        buf = ""
        for ch in result:
            buf += ch
            if buf in ("🟩", "🟨", "⬛"):
                emoji_list.append(buf)
                buf = ""
        for ch, em in zip(guess, emoji_list):
            ch = ch.upper()
            if PRIORITY.get(em, 0) > PRIORITY.get(mp.get(ch, "⬛"), 0):
                mp[ch] = em
    return mp

def _keyboard_display(guesses: List[Dict[str, Any]]) -> str:
    """Linha de letras usadas com indicador de status."""
    mp = _letter_map(guesses)
    if not mp:
        return ""
    green  = [f"{l}" for l, s in sorted(mp.items()) if s == "🟩"]
    yellow = [f"{l}" for l, s in sorted(mp.items()) if s == "🟨"]
    gray   = [f"{l}" for l, s in sorted(mp.items()) if s == "⬛"]
    parts  = []
    if green:  parts.append("🟩 " + " ".join(green))
    if yellow: parts.append("🟨 " + " ".join(yellow))
    if gray:   parts.append("⬛ " + " ".join(gray))
    return "\n".join(parts)

def _history_text(guesses: List[Dict[str, Any]]) -> str:
    if not guesses:
        return "⬛⬛⬛⬛⬛⬛"
    lines: List[str] = []
    for item in guesses:
        lines.append(f"<code>{str(item['guess']).upper()}</code>")
        lines.append(str(item["result"]))
        lines.append("")
    return "\n".join(lines).rstrip()

def _share_text(guesses: List[Dict[str, Any]], attempts: int, win: bool, streak: int) -> str:
    rows  = [str(x["result"]) for x in guesses]
    grid  = "\n".join(rows)
    score = f"{attempts}/6" if win else "X/6"
    return (
        "🎌 TERMO ANIME — SourceBaltigo\n\n"
        f"{grid}\n\n"
        f"Resultado: {score}\n"
        f"🔥 Sequência: {streak} dia(s)"
    )

def _share_kb(share_text: str) -> InlineKeyboardMarkup:
    url = f"https://t.me/share/url?text={quote_plus(share_text)}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 Compartilhar resultado", url=url)
    ]])

def _display_name(row: Dict[str, Any]) -> str:
    username  = (row.get("username")  or "").strip()
    full_name = (row.get("full_name") or "").strip()
    if username:  return f"@{username}"
    if full_name: return full_name
    return f"Usuário {int(row.get('user_id') or 0)}"

def _difficulty_stars(d: int) -> str:
    return "⭐" * d + "☆" * (3 - d)


# ─────────────────────────────────────────────
#  Textos de UI
# ─────────────────────────────────────────────

def _intro_text() -> str:
    return (
        "🎌 <b>TERMO ANIME</b>\n"
        "<i>SourceBaltigo</i>\n\n"
        "Descubra a palavra secreta de <b>6 letras</b>\n"
        "do universo dos animes em até <b>6 tentativas</b>.\n\n"
        "⏱ <b>5 minutos</b> para resolver\n"
        "🟩 Letra certa na posição certa\n"
        "🟨 Letra existe, posição errada\n"
        "⬛ Letra não está na palavra\n\n"
        "🪙 Recompensa em Coins por acertar\n"
        f"⭐ <b>+{XP_REWARD} XP</b> por vitória\n"
        "🔥 Bônus para sequências diárias\n\n"
        "<i>Palavra nova todo dia às 00h (horário de SP)</i>"
    )

def _start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮  Jogar agora",      callback_data="termo:start")],
        [
            InlineKeyboardButton("📊 Estatísticas", callback_data="termo:stats"),
            InlineKeyboardButton("🏆 Ranking",      callback_data="termo:ranking"),
        ],
        [InlineKeyboardButton("❓  Como jogar",       callback_data="termo:help")],
    ])

def _board_text(game: Dict[str, Any]) -> str:
    attempts = len(game["guesses"])
    secs     = _seconds_left(game["start_time"])
    timer_em = "⏱" if secs > 60 else "⚠️"
    training_badge = "\n🧪 <i>Modo treino — resultado não salvo</i>" if game["mode"] == "train" else ""

    kb = _keyboard_display(game["guesses"])
    kb_section = f"\n\n<b>Letras usadas:</b>\n{kb}" if kb else ""

    return (
        "🎌 <b>TERMO ANIME</b>\n\n"
        f"{_history_text(game['guesses'])}\n\n"
        f"Tentativa <b>{attempts}/6</b> · {timer_em} <b>{_fmt_mmss(secs)}</b>"
        f"{kb_section}"
        f"{training_badge}"
    )

def _stats_text(user_id: int) -> str:
    ensure_termo_stats_row(user_id)
    stats = get_termo_stats(user_id) or {}
    rank  = get_termo_user_rank(user_id)

    games    = int(stats.get("games_played")    or 0)
    wins     = int(stats.get("wins")            or 0)
    losses   = int(stats.get("losses")          or 0)
    streak   = int(stats.get("current_streak")  or 0)
    best_str = int(stats.get("best_streak")     or 0)
    best_sc  = int(stats.get("best_score")      or 0)

    buckets  = [int(stats.get(f"{k}_try") or 0)
                for k in ("one","two","three","four","five","six")]
    win_rate = int(round(wins / games * 100)) if games > 0 else 0

    # Barra de distribuição
    max_b = max(buckets) if any(b > 0 for b in buckets) else 1
    dist_lines = []
    for i, count in enumerate(buckets, 1):
        bar_len = int((count / max_b) * 10) if max_b > 0 else 0
        bar     = "█" * bar_len + "░" * (10 - bar_len)
        dist_lines.append(f"{i} │{bar}│ {count}")

    best_sc_txt = str(best_sc) if best_sc > 0 else "—"
    rank_txt    = f"#{rank}"   if rank   > 0 else "—"

    return (
        "📊 <b>Suas Estatísticas — Termo Anime</b>\n\n"
        f"🎮 Partidas jogadas: <b>{games}</b>\n"
        f"✅ Vitórias: <b>{wins}</b>  ❌ Derrotas: <b>{losses}</b>\n"
        f"📈 Taxa de acerto: <b>{win_rate}%</b>\n\n"
        f"🔥 Sequência atual: <b>{streak}</b> dia(s)\n"
        f"🏅 Melhor sequência: <b>{best_str}</b> dia(s)\n"
        f"🎯 Melhor score: <b>{best_sc_txt}</b>\n"
        f"🌍 Ranking global: <b>{rank_txt}</b>\n\n"
        "📦 <b>Distribuição de tentativas</b>\n"
        "<code>\n" + "\n".join(dist_lines) + "\n</code>"
    )

def _ranking_text(rows: List[Dict[str, Any]], title: str) -> str:
    if not rows:
        return f"🏆 <b>{title}</b>\n\n<i>Sem resultados ainda. Seja o primeiro!</i>"

    medals = ["🥇", "🥈", "🥉"]
    lines  = [f"🏆 <b>{title}</b>\n"]

    for i, row in enumerate(rows, start=1):
        icon   = medals[i - 1] if i <= 3 else f"  {i}."
        wins   = int(row.get("wins") or 0)
        name   = _display_name(row)
        streak = int(row.get("best_streak") or 0)
        score  = int(row.get("best_score")  or 0)

        score_txt  = f" · 🎯 {score}" if score > 0 else ""
        streak_txt = f" · 🔥 {streak}" if streak > 0 else ""
        lines.append(f"{icon} {name} — <b>{wins}</b> vitória(s){streak_txt}{score_txt}")

    return "\n".join(lines)

def _help_text() -> str:
    return (
        "❓ <b>Como jogar — Termo Anime</b>\n\n"
        "Digite uma palavra de <b>6 letras</b> relacionada ao universo dos animes.\n"
        "Após cada tentativa você recebe pistas:\n\n"
        "🟩 Letra certa na posição correta\n"
        "🟨 Letra existe, mas na posição errada\n"
        "⬛ Letra não está na palavra\n\n"
        "<b>Comandos disponíveis:</b>\n"
        "/termo — Menu principal\n"
        "/termostats — Suas estatísticas\n"
        "/termoranking — Ranking global\n"
        "/termosemana — Ranking da semana\n"
        "/termomes — Ranking do mês\n"
        "/termodica — Pedir uma dica (custa coins)\n\n"
        "⏱ Você tem <b>5 minutos</b> e <b>6 tentativas</b>.\n"
        "🪙 Acertando você ganha Coins e XP.\n"
        "🔥 Jogue todo dia para manter sua sequência!"
    )


# ─────────────────────────────────────────────
#  Persistência / cache
# ─────────────────────────────────────────────

def _cache_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    guesses = row.get("guesses") or []
    if isinstance(guesses, str):
        try:
            guesses = json.loads(guesses)
        except Exception:
            guesses = []
    game = {
        "id":         int(row["id"]),
        "user_id":    int(row["user_id"]),
        "date":       row["date"],
        "word":       str(row["word"]).lower(),
        "category":   str(row.get("category") or "Desconhecido"),
        "source":     str(row.get("source")   or "Anime"),
        "difficulty": int(row.get("difficulty") or 1),
        "hint":       str(row.get("hint")     or ""),
        "guesses":    guesses,
        "mode":       str(row.get("mode")   or "daily"),
        "status":     str(row.get("status") or "playing"),
        "start_time": int(row["start_time"]),
        "hint_used":  bool(row.get("hint_used") or False),
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
    return _cache_from_row(row)

def _persist_progress(game: Dict[str, Any]) -> None:
    if game.get("mode") == "train" or not (gid := int(game.get("id") or 0)):
        return
    update_termo_game_progress(
        game_id=gid,
        attempts=len(game["guesses"]),
        guesses_json=json.dumps(game["guesses"], ensure_ascii=False),
        used_letters=_used_letters_raw(game["guesses"]),
    )

def _used_letters_raw(guesses: List[Dict[str, Any]]) -> str:
    seen: Set[str] = set()
    ordered: List[str] = []
    for item in guesses:
        for ch in str(item.get("guess", "")).upper():
            if ch.isalpha() and ch not in seen:
                seen.add(ch)
                ordered.append(ch)
    return " ".join(ordered)

def _finish_game(game: Dict[str, Any], status: str,
                 reward_coins: int = 0, reward_xp: int = 0) -> None:
    user_id = int(game["user_id"])
    if game.get("mode") == "train":
        ACTIVE_GAMES.pop(user_id, None)
        return
    gid = int(game.get("id") or 0)
    if gid <= 0:
        ACTIVE_GAMES.pop(user_id, None)
        return
    spent = max(0, int(time.time()) - int(game["start_time"]))
    finish_termo_game(
        game_id=gid,
        status=status,
        attempts=len(game["guesses"]),
        guesses_json=json.dumps(game["guesses"], ensure_ascii=False),
        used_letters=_used_letters_raw(game["guesses"]),
        time_spent_seconds=spent,
        reward_coins=reward_coins,
        reward_xp=reward_xp,
        won_at_attempt=len(game["guesses"]) if status == "win" else 0,
    )
    ACTIVE_GAMES.pop(user_id, None)


# ═════════════════════════════════════════════
#  INICIAR PARTIDAS
# ═════════════════════════════════════════════

async def _start_daily(update: Update, use_edit: bool = False) -> None:
    user = update.effective_user
    if not user:
        return
    user_id = int(user.id)
    today   = _sp_today()

    existing = get_termo_daily_game(user_id, today)
    if existing:
        st = str(existing.get("status", ""))
        if st == "playing":
            game = _cache_from_row(existing)
            text = _board_text(game)
            kb   = None
        else:
            text = (
                "📅 <b>Você já jogou hoje!</b>\n\n"
                f"Próxima palavra em <b>{_next_reset_text()}</b>.\n\n"
                "Use /termostats para ver suas estatísticas."
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📊 Ver estatísticas", callback_data="termo:stats"),
                InlineKeyboardButton("🏆 Ranking", callback_data="termo:ranking"),
            ]])
        await _send_or_edit(update, use_edit, text, kb)
        return

    # Nova partida
    word_data = _pick_daily_word(user_id)
    start_ts  = int(time.time())
    # Buscar dica e dificuldade do índice
    word_entry = _WORD_INDEX.get(word_data["word"], word_data)

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

    created = get_termo_daily_game(user_id, today)
    ACTIVE_GAMES[user_id] = {
        "id":         int(created["id"]) if created and created.get("id") else 0,
        "user_id":    user_id,
        "date":       today,
        "word":       word_data["word"],
        "category":   word_data["category"],
        "source":     word_data["source"],
        "difficulty": word_entry.get("difficulty", 1),
        "hint":       word_entry.get("hint", ""),
        "guesses":    [],
        "mode":       "daily",
        "status":     "playing",
        "start_time": start_ts,
        "hint_used":  False,
    }

    diff_stars = _difficulty_stars(word_entry.get("difficulty", 1))
    text = (
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        f"Tentativa <b>0/6</b> · ⏱ <b>5:00</b>\n"
        f"Dificuldade: {diff_stars}\n\n"
        "✏️ <i>Digite uma palavra de 6 letras:</i>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💡 Pedir dica", callback_data="termo:hint"),
    ]])
    await _send_or_edit(update, use_edit, text, kb)


async def _start_train(update: Update, use_edit: bool = False) -> None:
    user = update.effective_user
    if not user:
        return
    user_id = int(user.id)

    if not _is_admin(user_id):
        text = "❌ Apenas administradores podem usar o modo treino."
        await _send_or_edit(update, use_edit, text)
        return

    word_data  = _pick_train_word()
    word_entry = _WORD_INDEX.get(word_data["word"], word_data)
    ACTIVE_GAMES[user_id] = {
        "id":         0,
        "user_id":    user_id,
        "date":       _sp_today(),
        "word":       word_data["word"],
        "category":   word_data["category"],
        "source":     word_data["source"],
        "difficulty": word_entry.get("difficulty", 1),
        "hint":       word_entry.get("hint", ""),
        "guesses":    [],
        "mode":       "train",
        "status":     "playing",
        "start_time": int(time.time()),
        "hint_used":  False,
    }

    diff_stars = _difficulty_stars(word_entry.get("difficulty", 1))
    text = (
        "🧪 <b>TERMO TREINO</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        f"Tentativa <b>0/6</b> · ⏱ <b>5:00</b>\n"
        f"Dificuldade: {diff_stars}\n\n"
        "✏️ <i>Digite uma palavra de 6 letras:</i>"
    )
    await _send_or_edit(update, use_edit, text)


async def _send_or_edit(update: Update, use_edit: bool,
                        text: str,
                        kb: Optional[InlineKeyboardMarkup] = None) -> None:
    if use_edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=kb
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=kb
        )


# ═════════════════════════════════════════════
#  COMMAND HANDLERS
# ═════════════════════════════════════════════

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    user_id = int(update.effective_user.id)
    game    = _get_active_game(user_id)
    if game:
        await update.message.reply_text(_board_text(game), parse_mode="HTML")
        return
    await update.message.reply_text(
        _intro_text(), parse_mode="HTML", reply_markup=_start_buttons()
    )

async def termo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    await update.message.reply_text(
        _stats_text(int(update.effective_user.id)), parse_mode="HTML"
    )

async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    await update.message.reply_text(
        _ranking_text(get_termo_global_ranking(10), "Ranking Global — Termo Anime"),
        parse_mode="HTML",
    )

async def termo_ranking_week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(7, 10), "Ranking da Semana — Termo Anime"),
        parse_mode="HTML",
    )

async def termo_ranking_month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(30, 10), "Ranking do Mês — Termo Anime"),
        parse_mode="HTML",
    )

async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    await _start_train(update, use_edit=False)

async def termo_treino_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
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
    if not await _gate_ok(update):
        return
    user_id = int(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ Apenas admins podem usar isso.")
        return
    game = ACTIVE_GAMES.get(user_id)
    if game and game.get("mode") == "train":
        ACTIVE_GAMES.pop(user_id, None)
        await update.message.reply_text(
            f"🧪 Treino encerrado.\n\n"
            f"A palavra era: <b>{game['word'].upper()}</b>\n"
            f"Categoria: <b>{game['category']}</b> · Origem: <b>{game['source']}</b>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("❌ Nenhum treino ativo.")

async def termo_help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gate_ok(update):
        return
    await update.message.reply_text(_help_text(), parse_mode="HTML")

async def termo_hint_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pedir dica durante uma partida ativa."""
    if not await _gate_ok(update):
        return
    user_id = int(update.effective_user.id)
    game    = _get_active_game(user_id)
    if not game:
        await update.message.reply_text("❌ Nenhuma partida em andamento. Use /termo para começar.")
        return
    await _give_hint(update.effective_message, game, user_id)

async def _give_hint(msg, game: Dict[str, Any], user_id: int) -> None:
    if game.get("hint_used"):
        await msg.reply_text("💡 Você já usou sua dica nesta partida.")
        return

    hint = game.get("hint", "")
    if not hint:
        await msg.reply_text(
            "💡 Não há dica disponível para esta palavra.\n"
            f"Categoria: <b>{game['category']}</b> · Origem: <b>{game['source']}</b>",
            parse_mode="HTML",
        )
        return

    # Cobrar coins em partida diária
    if game.get("mode") == "daily":
        # Tentamos descontar; se saldo insuficiente avisamos mas não bloqueamos
        # (depende da API de coins disponível no database.py)
        try:
            add_user_coins(user_id, -HINT_COST_COINS)
        except Exception:
            pass

    game["hint_used"] = True
    cost_note = f"\n<i>(-{HINT_COST_COINS} coins)</i>" if game.get("mode") == "daily" else ""

    await msg.reply_text(
        f"💡 <b>Dica:</b> {hint}\n"
        f"Categoria: <b>{game['category']}</b> · Origem: <b>{game['source']}</b>"
        f"{cost_note}",
        parse_mode="HTML",
    )


# ═════════════════════════════════════════════
#  CALLBACK HANDLER
# ═════════════════════════════════════════════

async def termo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _touch_identity(update)

    if not has_accepted_terms(int(query.from_user.id), TERMS_VERSION):
        await query.edit_message_text(
            "⛩️ Aceite os termos primeiro. Use /start."
        )
        return

    data    = str(query.data or "")
    user_id = int(query.from_user.id)

    if data == "termo:start":
        await _start_daily(update, use_edit=True)

    elif data == "termo:stats":
        await query.edit_message_text(
            _stats_text(user_id), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="termo:menu")
            ]])
        )

    elif data == "termo:ranking":
        await query.edit_message_text(
            _ranking_text(get_termo_global_ranking(10), "Ranking Global — Termo Anime"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📅 Semana",  callback_data="termo:rank_week"),
                InlineKeyboardButton("📆 Mês",     callback_data="termo:rank_month"),
            ], [
                InlineKeyboardButton("⬅️ Voltar", callback_data="termo:menu"),
            ]])
        )

    elif data == "termo:rank_week":
        await query.edit_message_text(
            _ranking_text(get_termo_period_ranking(7, 10), "Ranking da Semana"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌍 Global",  callback_data="termo:ranking"),
                InlineKeyboardButton("📆 Mês",     callback_data="termo:rank_month"),
            ]])
        )

    elif data == "termo:rank_month":
        await query.edit_message_text(
            _ranking_text(get_termo_period_ranking(30, 10), "Ranking do Mês"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🌍 Global",  callback_data="termo:ranking"),
                InlineKeyboardButton("📅 Semana",  callback_data="termo:rank_week"),
            ]])
        )

    elif data == "termo:help":
        await query.edit_message_text(
            _help_text(), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="termo:menu")
            ]])
        )

    elif data == "termo:menu":
        await query.edit_message_text(
            _intro_text(), parse_mode="HTML", reply_markup=_start_buttons()
        )

    elif data == "termo:hint":
        game = _get_active_game(user_id)
        if not game:
            await query.answer("Nenhuma partida ativa.", show_alert=True)
            return
        await _give_hint(query.message, game, user_id)

    elif data == "termo:train_start":
        await _start_train(update, use_edit=True)


# ═════════════════════════════════════════════
#  GUESS HANDLER
# ═════════════════════════════════════════════

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return
    _touch_identity(update)
    if not has_accepted_terms(int(update.effective_user.id), TERMS_VERSION):
        return

    guess   = _normalize(update.message.text)
    user_id = int(update.effective_user.id)

    if len(guess) != WORD_LENGTH or not _valid_format(guess):
        return

    _load_words()
    if guess not in VALID_WORDS:
        await update.message.reply_text(
            "❌ <b>Palavra inválida</b> — não está na lista do jogo.\n"
            "<i>Use personagens, termos ou gêneros do universo anime.</i>",
            parse_mode="HTML",
        )
        return

    game = _get_active_game(user_id)
    if not game:
        return

    if not _anti_flood_ok(user_id):
        return

    if guess in {str(x["guess"]).lower() for x in game["guesses"]}:
        await update.message.reply_text("♻️ Palavra já tentada nesta partida.")
        return

    # Verificar tempo
    if _seconds_left(game["start_time"]) <= 0:
        if game["mode"] != "train":
            record_termo_result(user_id, False, len(game["guesses"]))
        _finish_game(game, "timeout")
        await update.message.reply_text(
            "⏰ <b>Tempo esgotado!</b>\n\n"
            f"A palavra era: <b>{game['word'].upper()}</b>\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>\n\n"
            f"📅 Próxima palavra em <b>{_next_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    result = _evaluate(game["word"], guess)
    game["guesses"].append({"guess": guess, "result": result, "ts": int(time.time())})
    _persist_progress(game)

    # ── VITÓRIA ──────────────────────────────────
    if guess == game["word"]:
        training     = game["mode"] == "train"
        streak       = 0
        reward_coins = 0
        bonus_coins  = 0

        if not training:
            record_termo_result(user_id, True, len(game["guesses"]))
            stats        = get_termo_stats(user_id) or {}
            streak       = int(stats.get("current_streak") or 0)
            reward_coins = _daily_coins(len(game["guesses"]))
            bonus_coins  = _streak_bonus(streak)
            add_user_coins(user_id, reward_coins + bonus_coins)
            add_progress_xp(user_id, XP_REWARD)

        share = _share_text(game["guesses"], len(game["guesses"]), True, streak)
        _finish_game(game, "win", reward_coins + bonus_coins,
                     0 if training else XP_REWARD)

        attempts    = len(game["guesses"])
        perf_emoji  = ["🎯", "🔥", "⭐", "👏", "😅", "😌"][min(attempts - 1, 5)]
        diff_stars  = _difficulty_stars(game.get("difficulty", 1))

        if training:
            await update.message.reply_text(
                f"{perf_emoji} <b>Acertou no modo treino!</b>\n\n"
                f"{_history_text(game['guesses'])}\n\n"
                f"Palavra: <b>{game['word'].upper()}</b>\n"
                f"Categoria: <b>{game['category']}</b> · {diff_stars}\n"
                f"Origem: <b>{game['source']}</b>\n\n"
                f"📤 Compartilhe:\n<code>{share}</code>",
                parse_mode="HTML",
                reply_markup=_share_kb(share),
            )
        else:
            bonus_line = f"\n🎁 Bônus sequência: <b>+{bonus_coins}</b> 🪙" if bonus_coins > 0 else ""
            streak_msg = (
                f"🔥 Sequência: <b>{streak}</b> dia(s)" if streak > 1
                else "🔥 Sequência iniciada! Continue jogando amanhã."
            )
            await update.message.reply_text(
                f"{perf_emoji} <b>Palavra encontrada em {attempts}/6!</b>\n\n"
                f"{_history_text(game['guesses'])}\n\n"
                f"Palavra: <b>{game['word'].upper()}</b>\n"
                f"Categoria: <b>{game['category']}</b> · {diff_stars}\n"
                f"Origem: <b>{game['source']}</b>\n\n"
                f"🪙 +<b>{reward_coins}</b> Coins{bonus_line}\n"
                f"⭐ +<b>{XP_REWARD}</b> XP\n"
                f"{streak_msg}\n\n"
                f"📤 <b>Compartilhe seu resultado:</b>\n<code>{share}</code>",
                parse_mode="HTML",
                reply_markup=_share_kb(share),
            )
        return

    # ── DERROTA (tentativas esgotadas) ───────────
    if len(game["guesses"]) >= MAX_ATTEMPTS:
        training  = game["mode"] == "train"
        old_stats = get_termo_stats(user_id) or {}
        old_streak = int(old_stats.get("current_streak") or 0)

        if not training:
            record_termo_result(user_id, False, len(game["guesses"]))
        _finish_game(game, "lose")

        streak_lost = (
            f"\n💔 Sequência de <b>{old_streak}</b> dia(s) perdida!"
            if old_streak > 0 and not training else ""
        )
        await update.message.reply_text(
            f"💀 <b>Fim de jogo!</b>\n\n"
            f"{_history_text(game['guesses'])}\n\n"
            f"A palavra era: <b>{game['word'].upper()}</b>\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>"
            f"{streak_lost}\n\n"
            f"📅 Próxima palavra em <b>{_next_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    # ── CONTINUAR ────────────────────────────────
    await update.message.reply_text(_board_text(game), parse_mode="HTML")
