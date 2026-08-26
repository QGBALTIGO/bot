from __future__ import annotations

import os
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from identity_repository import sync_telegram_identity
from utils.gatekeeper import gatekeeper


BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
BOT_USERNAME = os.getenv("BOT_USERNAME", "SourceBaltigo_Bot").strip().lstrip("@")


@dataclass(frozen=True)
class WebAppEntry:
    title: str
    description: str
    button: str
    path: str
    icon: str = "🎮"
    banner_url: str = ""


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def open_webapp_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    entry: WebAppEntry,
) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    if _is_group(update):
        private_url = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "https://t.me/"
        text = (
            f"{entry.icon} <b>{entry.title}</b>\n\n"
            "Essa área usa seu perfil e seus recursos pessoais, então abre somente no privado."
        )
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔒 Abrir no privado", url=private_url)]]
        )
        await msg.reply_html(text, reply_markup=keyboard)
        return

    ok, blocked = await gatekeeper(update, context)
    if not ok:
        if blocked:
            await msg.reply_html(blocked)
        return

    try:
        sync_telegram_identity(
            int(user.id),
            username=str(user.username or ""),
            full_name=str(user.full_name or ""),
        )
    except Exception:
        # Identidade enriquecida melhora perfil/ranking, mas não deve tornar uma
        # MiniApp inteira indisponível se o sync auxiliar falhar pontualmente.
        pass

    if not BASE_URL:
        await msg.reply_text("⚠️ MiniApp indisponível: BASE_URL não configurada.")
        return

    url = f"{BASE_URL}{entry.path}"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(entry.button, web_app=WebAppInfo(url=url))]]
    )
    text = f"{entry.icon} <b>{entry.title}</b>\n\n{entry.description}"

    if entry.banner_url:
        try:
            await msg.reply_photo(
                photo=entry.banner_url,
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass

    await msg.reply_html(text, reply_markup=keyboard)
