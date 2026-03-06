async def nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    user_id = user.id

    ensure_user_row(user_id, user.first_name)

    row = get_user_row(user_id)

    comandos = int(row["commands"] or 0)
    level = int(row["level"] or 1)

    rank_tag = get_rank_tag(level)

    proximo = level * COMANDOS_POR_NIVEL
    progresso = comandos % COMANDOS_POR_NIVEL

    barra = progress_bar(progresso, COMANDOS_POR_NIVEL)

    ranking = get_level_rank(user_id)

    msg = (
        "🏆 <b>PERFIL DE NÍVEL</b>\n\n"

        f"👤 <b>{row['nick']}</b>\n"
        f"{rank_tag}\n\n"

        f"⭐ <b>Nível</b>: {level}\n"
        f"🏅 <b>Ranking</b>: #{ranking}\n\n"

        f"{barra}\n"
        f"{progresso}/{COMANDOS_POR_NIVEL}"
    )

    await update.message.reply_html(msg)
