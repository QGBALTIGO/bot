from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

async def pedido(update, context):
    url = f"{BASE_URL}/pedido"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Abrir Central de Pedidos", web_app=WebAppInfo(url=url))]
    ])

    await update.message.reply_text(
        "📥 **Central de Pedidos**\n\n"
        "Peça animes, mangás ou reporte erros.\n"
        "Toque no botão abaixo para abrir.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
