from __future__ import annotations

import asyncio
import html
import logging
from typing import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import (
    get_all_coin_ranking_rows,
    get_all_collection_ranking_rows,
    get_all_memory_ranking_rows,
    get_termo_global_ranking,
    get_top_level_users,
)
from utils.runtime_guard import rate_limiter

logger = logging.getLogger(__name__)

RANKING_IMAGE = (
    "https://photo.chelpbot.me/"
    "AgACAgEAAxkBZqlp8GmfqqNQyQV05efRn6slkZYc66uOAALOC2sbS__4RP55dhAgyc7mAQADAgADeQADOgQ/photo.jpg"
)
RANKING_METRICS = {"geral", "termo", "memoria", "coins", "level", "colecao"}
RANKING_CALLBACK_WINDOW_SECONDS = 1.2
GENERAL_RANKING_SAMPLE_SIZE = 100


def _escape(value: object, *, limit: int = 80) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        text = text[: max(1, limit - 1)].rstrip() + "…"
    return html.escape(text, quote=False)


def _safe_name(row: dict) -> str:
    nickname = str(row.get("nickname") or "").strip()
    if nickname:
        return _escape(nickname)

    full_name = str(row.get("full_name") or "").strip()
    if full_name:
        return _escape(full_name)

    username = str(row.get("username") or "").strip().lstrip("@")
    if username:
        return "@" + _escape(username, limit=64)

    try:
        user_id = int(row.get("user_id") or 0)
    except (TypeError, ValueError):
        user_id = 0
    return f"User {user_id}" if user_id > 0 else "Jogador"


def _fancy_name(row: dict) -> str:
    nickname = str(row.get("nickname") or "").strip()
    if nickname:
        return f"「{_escape(nickname)}」"
    return _safe_name(row)


def _format_duration_ms(value: object) -> str:
    try:
        total_ms = max(0, int(round(float(value or 0))))
    except (TypeError, ValueError):
        total_ms = 0

    if total_ms <= 0:
        return "--"

    total_seconds = total_ms // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_avg_number(value: object) -> str:
    try:
        number = max(0.0, float(value or 0))
    except (TypeError, ValueError):
        number = 0.0

    rounded = round(number)
    if abs(number - rounded) < 0.05:
        return str(int(rounded))
    return f"{number:.1f}"


def _ranking_kb(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏆 Geral", callback_data=f"rank:geral:{owner_id}")],
            [
                InlineKeyboardButton("🎯 Termo", callback_data=f"rank:termo:{owner_id}"),
                InlineKeyboardButton("🧠 Memória", callback_data=f"rank:memoria:{owner_id}"),
            ],
            [
                InlineKeyboardButton("🪙 Coins", callback_data=f"rank:coins:{owner_id}"),
                InlineKeyboardButton("⭐ Nível", callback_data=f"rank:level:{owner_id}"),
            ],
            [InlineKeyboardButton("📚 Coleção", callback_data=f"rank:colecao:{owner_id}")],
        ]
    )


def _format_rank_header(metric: str) -> str:
    labels = {
        "geral": "🏆 RANKING — GERAL",
        "termo": "🎯 RANKING — TERMO",
        "memoria": "🧠 RANKING — MEMÓRIA",
        "coins": "🪙 RANKING — COINS",
        "level": "⭐ RANKING — NÍVEL",
        "colecao": "📚 RANKING — COLEÇÃO",
    }
    return f"<b>{labels.get(metric, labels['geral'])} (TOP 10)</b>\n\n"


def _position_score_map(rows: list[dict]) -> dict[int, float]:
    """Convert positions to comparable percentile scores from 0 to 100."""

    total = len(rows)
    if total <= 0:
        return {}

    scores: dict[int, float] = {}
    for position, row in enumerate(rows, start=1):
        try:
            user_id = int(row.get("user_id") or 0)
        except (TypeError, ValueError):
            continue
        if user_id <= 0 or user_id in scores:
            continue
        if total == 1:
            score = 100.0
        else:
            score = 100.0 * (total - position) / (total - 1)
        scores[user_id] = score
    return scores


def _top_rows(loader: Callable[[], list[dict]], limit: int) -> list[dict]:
    rows = loader() or []
    return [dict(row) for row in rows[:limit] if isinstance(row, dict)]


def _build_general_ranking() -> list[dict]:
    termo_rows = [dict(row) for row in (get_termo_global_ranking(GENERAL_RANKING_SAMPLE_SIZE) or [])]
    coin_rows = _top_rows(get_all_coin_ranking_rows, GENERAL_RANKING_SAMPLE_SIZE)
    collection_rows = _top_rows(get_all_collection_ranking_rows, GENERAL_RANKING_SAMPLE_SIZE)
    level_rows = [dict(row) for row in (get_top_level_users(GENERAL_RANKING_SAMPLE_SIZE) or [])]
    memory_rows = _top_rows(get_all_memory_ranking_rows, GENERAL_RANKING_SAMPLE_SIZE)

    metric_rows = {
        "termo": termo_rows,
        "coins": coin_rows,
        "collection": collection_rows,
        "level": level_rows,
        "memory": memory_rows,
    }
    metric_scores = {name: _position_score_map(rows) for name, rows in metric_rows.items()}

    display_map: dict[int, dict] = {}
    all_user_ids: set[int] = set()
    for rows in metric_rows.values():
        for row in rows:
            try:
                user_id = int(row.get("user_id") or 0)
            except (TypeError, ValueError):
                continue
            if user_id <= 0:
                continue
            all_user_ids.add(user_id)
            display_map.setdefault(user_id, row)

    result: list[dict] = []
    for user_id in all_user_ids:
        scores = {name: values.get(user_id, 0.0) for name, values in metric_scores.items()}
        average = sum(scores.values()) / len(metric_scores)
        result.append(
            {
                "user_id": user_id,
                "row": display_map.get(user_id, {"user_id": user_id}),
                "avg_score": average,
                **{f"{name}_score": score for name, score in scores.items()},
            }
        )

    result.sort(
        key=lambda row: (
            row["avg_score"],
            row["termo_score"],
            row["memory_score"],
            row["coins_score"],
            row["collection_score"],
            row["level_score"],
            -row["user_id"],
        ),
        reverse=True,
    )
    return result[:10]


def _medal(position: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, f"<b>{position}.</b>")


def _render_general_ranking(rows: list[dict]) -> str:
    text = _format_rank_header("geral")
    if not rows:
        return text + "⚠️ Sem dados no momento."

    text += "Pontuação normalizada entre:\n"
    text += "🎯 Termo • 🧠 Memória • 🪙 Coins • ⭐ Nível • 📚 Coleção\n\n"

    lines: list[str] = []
    for position, row in enumerate(rows, start=1):
        name = _fancy_name(row["row"])
        score = float(row.get("avg_score") or 0.0)
        if position <= 3:
            lines.append(f"{_medal(position)} <b>{name}</b>\n└ Pontuação geral: <b>{score:.2f}</b>")
        else:
            lines.append(f"{_medal(position)} {name} — 🏆 <b>{score:.2f}</b>")
    return text + "\n\n".join(lines)


def _render_termo() -> str:
    rows = [dict(row) for row in (get_termo_global_ranking(10) or [])]
    text = _format_rank_header("termo")
    if not rows:
        return text + "⚠️ Sem dados no momento."

    lines = []
    for position, row in enumerate(rows, start=1):
        wins = max(0, int(row.get("wins") or 0))
        streak = max(0, int(row.get("best_streak") or 0))
        lines.append(f"{_medal(position)} {_safe_name(row)} — 🎯 <b>{wins}</b> vitórias | 🔥 {streak}")
    return text + "\n".join(lines)


def _render_memory() -> str:
    rows = _top_rows(get_all_memory_ranking_rows, 10)
    text = _format_rank_header("memoria")
    if not rows:
        return text + "⚠️ Sem dados no momento."

    lines = []
    for position, row in enumerate(rows, start=1):
        average_time = _format_duration_ms(row.get("avg_best_time_ms"))
        average_moves = _format_avg_number(row.get("avg_best_moves"))
        levels = max(0, int(row.get("levels_completed") or 0))
        lines.append(
            f"{_medal(position)} {_safe_name(row)} — ⏱️ <b>{average_time}</b> | "
            f"🎮 <b>{average_moves}</b> jogadas | 🧩 {levels} níveis"
        )
    return text + "\n".join(lines)


def _render_coins() -> str:
    rows = _top_rows(get_all_coin_ranking_rows, 10)
    text = _format_rank_header("coins")
    if not rows:
        return text + "⚠️ Sem dados no momento."

    lines = []
    for position, row in enumerate(rows, start=1):
        coins = max(0, int(row.get("coins") or 0))
        lines.append(f"{_medal(position)} {_safe_name(row)} — 🪙 <b>{coins:,}</b>".replace(",", "."))
    return text + "\n".join(lines)


def _render_level() -> str:
    rows = [dict(row) for row in (get_top_level_users(10) or [])]
    text = _format_rank_header("level")
    if not rows:
        return text + "⚠️ Sem dados no momento."

    lines = []
    for position, row in enumerate(rows, start=1):
        level = max(1, int(row.get("level") or 1))
        xp = max(0, int(row.get("xp") or 0))
        lines.append(f"{_medal(position)} {_safe_name(row)} — ⭐ <b>{level}</b> | XP {xp:,}".replace(",", "."))
    return text + "\n".join(lines)


def _render_collection() -> str:
    rows = _top_rows(get_all_collection_ranking_rows, 10)
    text = _format_rank_header("colecao")
    if not rows:
        return text + "⚠️ Sem dados no momento."

    lines = []
    for position, row in enumerate(rows, start=1):
        total = max(0, int(row.get("total_cards") or 0))
        lines.append(f"{_medal(position)} {_safe_name(row)} — 📚 <b>{total:,}</b>".replace(",", "."))
    return text + "\n".join(lines)


def _render_ranking(metric: str) -> str:
    renderers: dict[str, Callable[[], str]] = {
        "geral": lambda: _render_general_ranking(_build_general_ranking()),
        "termo": _render_termo,
        "memoria": _render_memory,
        "coins": _render_coins,
        "level": _render_level,
        "colecao": _render_collection,
    }
    return renderers.get(metric, renderers["geral"])()


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    from utils.gatekeeper import gatekeeper

    allowed, blocked_message = await gatekeeper(update, context)
    if not allowed:
        if blocked_message:
            await message.reply_html(blocked_message)
        return

    caption = "🏆 <b>RANKING</b>\n\nSelecione qual ranking você quer ver 👇"
    keyboard = _ranking_kb(user.id)

    try:
        await message.reply_photo(
            photo=RANKING_IMAGE,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Falha ao enviar imagem do ranking user_id=%s", user.id)
        await message.reply_html(caption, reply_markup=keyboard)


async def callback_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    try:
        prefix, metric, owner_raw = str(query.data or "").split(":", 2)
        owner_id = int(owner_raw)
    except (TypeError, ValueError):
        await query.answer("Ranking inválido.", show_alert=True)
        return

    if prefix != "rank" or metric not in RANKING_METRICS:
        await query.answer("Ranking inválido.", show_alert=True)
        return

    if user.id != owner_id:
        await query.answer("Apenas quem abriu o ranking pode usar estes botões.", show_alert=True)
        return

    allowed = await rate_limiter.allow(
        key=f"ranking-callback:{user.id}",
        limit=1,
        window_seconds=RANKING_CALLBACK_WINDOW_SECONDS,
    )
    if not allowed:
        await query.answer("Calma 🙂", show_alert=False)
        return

    await query.answer("Atualizando ranking…", show_alert=False)

    try:
        text = await asyncio.to_thread(_render_ranking, metric)
        keyboard = _ranking_kb(owner_id)
        message = query.message
        if not message:
            return

        if message.photo:
            await message.edit_caption(
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await message.edit_text(
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception:
        logger.exception("Falha ao atualizar ranking metric=%s user_id=%s", metric, user.id)
        if query.message:
            try:
                await query.message.reply_text("❌ Não consegui atualizar o ranking agora.")
            except Exception:
                logger.exception("Falha ao avisar erro do ranking user_id=%s", user.id)
