import os
import asyncio
from telethon import TelegramClient
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ======================================================
# 🔐 CONFIGURAÇÕES (USE VARIÁVEIS DE AMBIENTE)
# ======================================================
API_ID = int(os.getenv("API_ID", "34116600"))
API_HASH = os.getenv("API_HASH", "COLOQUE_SEU_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "COLOQUE_SEU_BOT_TOKEN")

CANAL_ANIME = os.getenv("CANAL_ANIME", "Centraldeanimes_Baltigo")
CANAL_MANGA = os.getenv("CANAL_MANGA", "MangasBrasil")

# ======================================================
# 🤖 TELETHON CLIENT (INICIA UMA VEZ)
# ======================================================
telethon_client = TelegramClient(
    "sessao_busca",
    API_ID,
    API_HASH
)

# ======================================================
# 🔎 FUNÇÕES DE BUSCA
# ======================================================
async def buscar_link(canal: str, termo: str):
    async for msg in telethon_client.iter_messages(canal, search=termo):
        if msg.text:
            return f"https://t.me/{canal}/{msg.id}"
    return None

# ======================================================
# 📌 COMANDOS
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👋 <b>Olá!</b>\n\n"
        "Sou um bot de busca de <b>animes</b> e <b>mangás</b>.\n\n"
        "📌 <b>Comandos disponíveis:</b>\n"
        "🎬 <code>/anime nome</code>\n"
        "📖 <code>/manga nome</code>\n\n"
        "✨ Exemplo:\n"
        "<code>/anime naruto</code>"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Uso incorreto</b>\n\n"
            "👉 <code>/anime nome do anime</code>"
        )
        return

    nome = " ".join(context.args).lower()
    await update.message.reply_text("🔎 Procurando o anime...")

    link = await buscar_link(CANAL_ANIME, nome)

    if link:
        await update.message.reply_html(
            f"🎬 <b>{nome.upper()}</b>\n\n"
            f"🔗 <b>Assista aqui:</b>\n{link}"
        )
    else:
        await update.message.reply_html(
            "🚫 <b>Anime não encontrado</b>\n"
            "Tente outro nome."
        )

async def manga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Uso incorreto</b>\n\n"
            "👉 <code>/manga nome do mangá</code>"
        )
        return

    nome = " ".join(context.args).lower()
    await update.message.reply_text("📚 Procurando o mangá...")

    link = await buscar_link(CANAL_MANGA, nome)

    if link:
        await update.message.reply_html(
            f"📖 <b>{nome.upper()}</b>\n\n"
            f"🔗 <b>Leia aqui:</b>\n{link}"
        )
    else:
        await update.message.reply_html(
            "🚫 <b>Mangá não encontrado</b>\n"
            "Tente outro nome."
        )

# ======================================================
# 🚀 MAIN
# ======================================================
async def main():
    await telethon_client.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("manga", manga))

    print("🤖 Bot rodando...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
