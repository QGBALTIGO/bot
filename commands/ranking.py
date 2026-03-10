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


def _fancy_name(row: dict) -> str:
    nick = str(row.get("nickname") or "").strip()
    if nick:
        return f"「{nick}」"

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
            InlineKeyboardButton("🏆 Geral", callback_data=f"rank:geral:{owner_id}"),
        ],
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
    if metric == "geral":
        return "🏆 <b>RANKING — GERAL (TOP 10)</b>\n\n"
    if metric == "termo":
        return "🎯 <b>RANKING — TERMO (TOP 10)</b>\n\n"
    if metric == "coins":
        return "🪙 <b>RANKING — COINS (TOP 10)</b>\n\n"
    if metric == "level":
        return "⭐ <b>RANKING — NÍVEL (TOP 10)</b>\n\n"
    return "📚 <b>RANKING — COLEÇÃO (TOP 10)</b>\n\n"


def _position_score_map(rows: list[dict]) -> dict[int, float]:
    total = len(rows)
    scores = {}

    if total <= 0:
        return scores

    for pos, row in enumerate(rows, start=1):
        uid = int(row["user_id"])
        scores[uid] = float(total - pos + 1)

    return scores


def _build_general_ranking() -> list[dict]:
    termo_rows = get_termo_global_ranking(100)
    coin_rows = get_all_coin_ranking_rows()
    collection_rows = get_all_collection_ranking_rows()
    level_rows = get_top_level_users(100)

    termo_scores = _position_score_map(termo_rows)
    coin_scores = _position_score_map(coin_rows)
    collection_scores = _position_score_map(collection_rows)
    level_scores = _position_score_map(level_rows)

    all_users = set()
    all_users.update(termo_scores.keys())
    all_users.update(coin_scores.keys())
    all_users.update(collection_scores.keys())
    all_users.update(level_scores.keys())

    display_map = {}

    for row in termo_rows + coin_rows + collection_rows + level_rows:
        uid = int(row["user_id"])
        if uid not in display_map:
            display_map[uid] = row

    result = []

    for uid in all_users:
        termo = termo_scores.get(uid, 0.0)
        coins = coin_scores.get(uid, 0.0)
        collection = collection_scores.get(uid, 0.0)
        level = level_scores.get(uid, 0.0)

        avg_score = (termo + coins + collection + level) / 4.0

        result.append({
            "user_id": uid,
            "row": display_map.get(uid, {"user_id": uid}),
            "avg_score": avg_score,
            "termo_score": termo,
            "coin_score": coins,
            "collection_score": collection,
            "level_score": level,
        })

    result.sort(
        key=lambda r: (
            r["avg_score"],
            r["termo_score"],
            r["coin_score"],
            r["collection_score"],
            r["level_score"],
            -r["user_id"],
        ),
        reverse=True,
    )

    return result[:10]


def _render_general_ranking(rows: list[dict]) -> str:
    text = _format_rank_header("geral")

    if not rows:
        return text + "⚠️ Sem dados no momento."

    text += "A classificação é baseada na média entre:\n"
    text += "🎯 Termo • 🪙 Coins • ⭐ Nível • 📚 Coleção\n\n"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for i, r in enumerate(rows, start=1):
        name = _fancy_name(r["row"])
        avg_score = r["avg_score"]

        if i in medals:
            text += (
                f"{medals[i]} <b>{name}</b>\n"
                f"└ Média geral: <b>{avg_score:.2f}</b>\n\n"
            )
        else:
            text += f"<b>{i}.</b> {name} — 🏆 <b>{avg_score:.2f}</b>\n"

    return text.strip()


def _render_ranking(metric: str) -> str:
    if metric == "geral":
        rows = _build_general_ranking()
        return _render_general_ranking(rows)

    if metric == "termo":
        rows = get_termo_global_ranking(10)
        text = _format_rank_header(metric)

        if not rows:
            return text + "⚠️ Sem dados no momento."

        for i, r in enumerate(rows, start=1):
            name = _safe_name(r)
            wins = int(r.get("wins") or 0)
            streak = int(r.get("best_streak") or 0)

            if i == 1:
                prefix = "🥇"
            elif i == 2:
                prefix = "🥈"
            elif i == 3:
                prefix = "🥉"
            else:
                prefix = f"<b>{i}.</b>"

            text += f"{prefix} {name} — 🎯 <b>{wins}</b> vitórias | 🔥 {streak}\n"

        return text

    if metric == "coins":
        rows = get_all_coin_ranking_rows()[:10]
        text = _format_rank_header(metric)

        if not rows:
            return text + "⚠️ Sem dados no momento."

        for i, r in enumerate(rows, start=1):
            name = _safe_name(r)
            coins = int(r.get("coins") or 0)

            if i == 1:
                prefix = "🥇"
            elif i == 2:
                prefix = "🥈"
            elif i == 3:
                prefix = "🥉"
            else:
                prefix = f"<b>{i}.</b>"

            text += f"{prefix} {name} — 🪙 <b>{coins}</b>\n"

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

            if i == 1:
                prefix = "🥇"
            elif i == 2:
                prefix = "🥈"
            elif i == 3:
                prefix = "🥉"
            else:
                prefix = f"<b>{i}.</b>"

            text += f"{prefix} {name} — ⭐ <b>{level}</b> | XP {xp}\n"

        return text

    rows = get_all_collection_ranking_rows()[:10]
    text = _format_rank_header("colecao")

    if not rows:
        return text + "⚠️ Sem dados no momento."

    for i, r in enumerate(rows, start=1):
        name = _safe_name(r)
        total = int(r.get("total_cards") or 0)

        if i == 1:
            prefix = "🥇"
        elif i == 2:
            prefix = "🥈"
        elif i == 3:
            prefix = "🥉"
        else:
            prefix = f"<b>{i}.</b>"

        text += f"{prefix} {name} — 📚 <b>{total}</b>\n"

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

    if metric not in ("geral", "termo", "coins", "level", "colecao"):
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
