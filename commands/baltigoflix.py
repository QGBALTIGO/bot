from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import BOT_BRAND
from utils.gatekeeper import ensure_channel_membership


def _is_group(update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in ("group", "supergroup"))


async def baltigoflix(update, context):
    if not await ensure_channel_membership(update, context):
        return

    msg = update.effective_message
    if not msg:
        return

    # 🔥 LINK DO SEU MINI APP
    webapp_url = "https://bot-production-1980.up.railway.app/baltigoflix"

    # 🔥 SEU BOT (pra grupo → privado)
    bot_private_url = "https://t.me/SourceBaltigo_Bot"

    # 🔥 BANNER (pode trocar depois)
    banner_url = "https://i.imgur.com/8Km9tLL.png"

    # 📌 Se for grupo → manda pro privado
    if _is_group(update):
        texto = (
            f"🔥 <b>{BOT_BRAND} Flix</b>\n\n"
            "Esse comando funciona apenas no <b>privado</b>.\n\n"
            "👇 Toque abaixo para abrir:"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Abrir no privado", url=bot_private_url)]
        ])

        await msg.reply_text(texto, parse_mode="HTML", reply_markup=kb)
        return

    # 🎬 Mensagem principal
    texto = (
        f"🎬 <b>{BOT_BRAND} Flix</b>\n\n"
        "Acesse a área premium com planos exclusivos.\n\n"
        "✨ Visual moderno\n"
        "⚡ Processo rápido\n"
        "📱 Tudo direto pelo bot\n\n"
        "👇 Toque abaixo para continuar:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Abrir BaltigoFlix", web_app=WebAppInfo(url=webapp_url))]
    ])

    await msg.reply_photo(
        photo=banner_url,
        caption=texto,
        parse_mode="HTML",
        reply_markup=kb,
    )
