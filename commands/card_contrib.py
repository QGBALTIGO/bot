async def sugerircard(update, context):

    if update.effective_chat.type != "private":
        return

    url = f"{WEBAPP_URL}/cards/contrib"

    await update.message.reply_text(
        "🖼 Central de Contribuições dos Cards\n\n"
        "Ajude a melhorar os personagens enviando novas imagens.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Abrir Central", web_app=WebAppInfo(url))]
        ])
    )
