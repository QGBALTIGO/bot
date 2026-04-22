import os
import unicodedata

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from utils.gatekeeper import gatekeeper


BASE_URL = (os.getenv("BASE_URL", "").strip() or os.getenv("WEBAPP_URL", "").strip()).rstrip("/")
if not BASE_URL:
    raise RuntimeError("BASE_URL nao configurado.")

MEMORIA_BANNER_URL = os.getenv(
    "MEMORIA_BANNER_URL",
    "https://photo.chelpbot.me/AgACAgEAAxkBarsAAXNp6UYolngW58ajeAQuGSywL1tCUwAC2AxrG0EGSUeuM-DG-3kWUgEAAwIAA3cAAzsE/photo.jpg",
).strip()

_LEVEL_MAP = {
    "facil": "easy",
    "medio": "medium",
    "dificil": "hard",
    "muitodificil": "extreme",
    "muito dificil": "extreme",
    "muito-dificil": "extreme",
    "easy": "easy",
    "medium": "medium",
    "hard": "hard",
    "extreme": "extreme",
}

_LEVEL_LABELS = {
    "easy": "Facil",
    "medium": "Medio",
    "hard": "Dificil",
    "extreme": "Muito dificil",
}


def _normalize_level(raw: str) -> str:
    value = str(raw or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = " ".join(value.split())
    return _LEVEL_MAP.get(value, "medium")


async def memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    ok, bloqueio = await gatekeeper(update, context)
    if not ok:
        if bloqueio:
            await msg.reply_html(bloqueio)
        return

    requested_level = _normalize_level(" ".join(context.args).strip()) if context.args else "medium"
    level_label = _LEVEL_LABELS.get(requested_level, "Médio")
    user_id = int(update.effective_user.id) if update.effective_user else 0
    url = f"{BASE_URL}/memoria?level={requested_level}&uid={user_id}"

    texto = (
        "🧠 <b>JOGO DA MEMORIA ANIME</b>\n\n"
        "Forme pares usando os banners das obras que ja existem no sistema de cards.\n\n"
        f"🎮 Dificuldade inicial: <b>{level_label}</b>\n\n""
        "Toque abaixo para abrir o mini app."
    )

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🧠 Abrir Jogo da Memória", web_app=WebAppInfo(url=url))]]
    )

    await msg.reply_photo(
        photo=MEMORIA_BANNER_URL,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
