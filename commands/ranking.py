import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import (
    get_termo_global_ranking,
    get_top_level_users,
    get_all_coin_ranking_rows,
    get_all_collection_ranking_rows,
)

RANKING_IMAGE = "https://photo.chelpbot.me/AgACAgEAAxkBZqlp8GmfqqNQyQV05efRn6slkZYc66uOAALOC2sbS__4RP55dhAgyc7mAQADAgADeQADOgQ/photo.jpg"

_RANK_BTN_LAST: dict[int, float] = {}


def _rank_btn_ok(user_id: int, seconds: float = 1.2) -> bool:
    now = time.time()
    last = _RANK_BTN_LAST.get(user_id, 0.0)
    if now - last < seconds:
        return False
    _RANK_BTN_LAST[user_id] = now
    return True


def _safe_name(row: dict) -> str:
    nick = str(row.get("nickname") or "").strip()
    if nick:
        return nick

    full_name = str(row.get("full_name") or "").strip()
    if full_name:
        return full_name

    username = str(row.get("username") or "").strip()
    if username:
        return f"@{username}"

    uid = int(row.get("user_id") or 0)
    return f"User {uid}"


def _ranking_kb(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Termo", callback_data=f"rank:termo:{owner_id}"),
            InlineKeyboardButton("🪙 Coins", callback_data=f"rank:coins:{owner_id}"),
        ],
        [
            InlineKeyboardButton("⭐ Nível", callback_data=f"rank:level:{owner_id}"),
            InlineKeyboardButton("📚 Coleção", callback_data=f"rank:colecao:{owner_id}"),
        ],
    ])


def _format_rank_header(metric: str) -> str:
    if metric == "termo":
        return "🏆 <b>RANKING — TERMO (TOP 10)</b>\n\n"
    if metric == "coins":
        return "🏆 <b>RANKING — COINS (TOP 10)</b>\n\n"
    if metric == "level":
        return "🏆 <b>RANKING — NÍVEL (TOP 10)</b>\n\n"
    return "🏆 <b>RANKING — COLEÇÃO (TOP 10)</b>\n\n"


def _render_ranking(metric: str) -> str:
    if metric == "termo":
        rows = get_termo_global_ranking(10)
        text = _format_rank_header(metric)

        if not rows:
            return text + "⚠️ Sem dados no momento."

        for i, r in enumerate(rows, start=1):
            name = _safe_name(r)
            wins = int(r.get("wins") or 0)
            streak = int(r.get("best_streak") or 0)
            text += f"<b>{i}.</b> {name} — 🎯 <b>{wins}</b> vitórias | 🔥 {streak}\n"

        return text

    if metric == "coins":
        rows = get_all_coin_ranking_rows()[:10]
        text = _format_rank_header(metric)

        if not rows:
            return text + "⚠️ Sem dados no momento."

        for i, r in enumerate(rows, start=1):
            name = _safe_name(r)
            coins = int(r.get("coins") or 0)
            text += f"<b>{i}.</b> {name} — 🪙 <b>{coins}</b>\n"

        return text

    if metric == "level":
        rows = get_top_level_users(10)
        text = _format_rank_header(metric)

        if not rows:
            return text + "⚠️ Sem dados no momento."

        for i, r in enumerate(rows, start=1):
            name = _safe_name(r)
            level = int(r.get("level") or 1)
            xp = int(r.get("xp") or 0)
            text += f"<b>{i}.</b> {name} — ⭐ <b>{level}</b> | XP {xp}\n"

        return text

    rows = get_all_collection_ranking_rows()[:10]
    text = _format_rank_header("colecao")

    if not rows:
        return text + "⚠️ Sem dados no momento."

    for i, r in enumerate(rows, start=1):
        name = _safe_name(r)
        total = int(r.get("total_cards") or 0)
        text += f"<b>{i}.</b> {name} — 📚 <b>{total}</b>\n"

    return text


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    owner_id = update.effective_user.id

    caption = (
        "🏆 <b>RANKING</b>\n\n"
        "Selecione qual ranking você quer ver 👇"
    )

    try:
        await update.message.reply_photo(
            photo=RANKING_IMAGE,
            caption=caption,
            parse_mode="HTML",
            reply_markup=_ranking_kb(owner_id),
        )
    except Exception:
        await update.message.reply_html(
            caption,
            reply_markup=_ranking_kb(owner_id),
        )


async def callback_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    await q.answer()

    user_id = q.from_user.id

    if not _rank_btn_ok(user_id, 1.2):
        await q.answer("Calma 🙂", show_alert=False)
        return

    try:
        _, metric, owner_s = (q.data or "").split(":")
        owner_id = int(owner_s)
    except Exception:
        await q.answer("Erro no ranking.", show_alert=True)
        return

    if user_id != owner_id:
        await q.answer("Apenas quem abriu o ranking pode mexer.", show_alert=True)
        return

    if metric not in ("termo", "coins", "level", "colecao"):
        await q.answer("Ranking inválido.", show_alert=True)
        return

    texto = _render_ranking(metric)

    try:
        if q.message and q.message.photo:
            await q.message.edit_caption(
                caption=texto,
                parse_mode="HTML",
                reply_markup=_ranking_kb(owner_id),
            )
        else:
            await q.message.edit_text(
                text=texto,
                parse_mode="HTML",
                reply_markup=_ranking_kb(owner_id),
            )
    except Exception:
        await q.answer("Não consegui atualizar agora.", show_alert=True)
