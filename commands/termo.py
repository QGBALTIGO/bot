        "category": word_data["category"],
        "source": word_data["source"],
        "guesses": [],
        "mode": "daily",
        "status": "playing",
        "start_time": int(time.time()),
    }

    text = (
        "🎌 <b>TERMO ANIME</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras."
    )

    if use_edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML")


async def _start_train(update: Update, use_edit: bool = False) -> None:
    user = update.effective_user
    if not user:
        return

    user_id = int(user.id)
    if not _is_admin(user_id):
        text = "❌ Apenas admins podem usar o modo treino."
        if use_edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        return

    word_data = _pick_train_word()
    ACTIVE_GAMES[user_id] = {
        "user_id": user_id,
        "date": _sp_today(),
        "word": word_data["word"],
        "category": word_data["category"],
        "source": word_data["source"],
        "guesses": [],
        "mode": "train",
        "status": "playing",
        "start_time": int(time.time()),
    }

    text = (
        "🧪 <b>TERMO TREINO</b>\n\n"
        "⬛⬛⬛⬛⬛⬛\n\n"
        "Tentativas: <b>0/6</b>\n"
        "Tempo restante: <b>5:00</b>\n\n"
        "Digite uma palavra de 6 letras."
    )

    if use_edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, parse_mode="HTML")


# =========================================================
# COMMAND HANDLERS
# =========================================================

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    user_id = int(update.effective_user.id)
    game = _get_active_game(user_id)

    if game:
        await update.message.reply_text(_board_text(game), parse_mode="HTML")
        return

    await update.message.reply_text(
        _intro_text(),
        parse_mode="HTML",
        reply_markup=_start_buttons(),
    )


async def termo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _stats_text(int(update.effective_user.id)),
        parse_mode="HTML",
    )


async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
        parse_mode="HTML",
    )


async def termo_ranking_week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(7, 10), "Ranking Termo — Semana"),
        parse_mode="HTML",
    )


async def termo_ranking_month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(30, 10), "Ranking Termo — Mês"),
        parse_mode="HTML",
    )


async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    await _start_train(update, use_edit=False)


async def termo_treino_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    user_id = int(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ Apenas admins podem usar isso.")
        return

    game = ACTIVE_GAMES.get(user_id)
    if not game or game.get("mode") != "train":
        await update.message.reply_text("❌ Nenhum treino ativo.")
        return

    await update.message.reply_text(_board_text(game), parse_mode="HTML")


async def termo_treino_stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _gatekeeper_ok(update):
        return

    user_id = int(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ Apenas admins podem usar isso.")
        return

    game = ACTIVE_GAMES.get(user_id)
    if game and game.get("mode") == "train":
        ACTIVE_GAMES.pop(user_id, None)
        await update.message.reply_text("🧪 Treino encerrado.")
    else:
        await update.message.reply_text("❌ Nenhum treino ativo.")


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def termo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    _touch_identity_from_update(update)

    if not has_accepted_terms(int(query.from_user.id), TERMS_VERSION):
        await query.edit_message_text(
            "❌ Você precisa aceitar os termos antes de usar o Termo.\n\n"
            "Use /start e conclua a etapa de aceite."
        )
        return

    data = str(query.data or "")

    if data == "termo:start":
        await _start_daily(update, use_edit=True)
        return

    if data == "termo:stats":
        await query.edit_message_text(
            _stats_text(int(query.from_user.id)),
            parse_mode="HTML",
        )
        return

    if data == "termo:ranking":
        await query.edit_message_text(
            _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
            parse_mode="HTML",
        )
        return

    if data == "termo:train_start":
        await _start_train(update, use_edit=True)
        return


# =========================================================
# GUESS HANDLER
# =========================================================

async def termo_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    _touch_identity_from_update(update)

    if not has_accepted_terms(int(update.effective_user.id), TERMS_VERSION):
        return

    guess = _normalize(update.message.text)
    user_id = int(update.effective_user.id)

    if len(guess) != WORD_LENGTH:
        return
    if not _valid_format(guess):
        return

    _load_words()
    if guess not in VALID_WORDS:
        await update.message.reply_text("❌ Palavra inválida.")
        return

    game = _get_active_game(user_id)
    if not game:
        return

    if not _anti_flood_ok(user_id):
        return

    if guess in {str(x["guess"]).lower() for x in game["guesses"]}:
        await update.message.reply_text("❌ Palavra já usada.")
        return

    if _seconds_left(game["start_time"]) <= 0:
        training = game["mode"] == "train"
        if not training:
            record_termo_result(user_id, False, len(game["guesses"]))
        _finish_game(game, "timeout")

        await update.message.reply_text(
            "⏱ <b>Tempo esgotado!</b>\n\n"
            f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>\n\n"
            f"📅 Próxima palavra em <b>{_next_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    result = _evaluate(game["word"], guess)
    game["guesses"].append({
        "guess": guess,
        "result": result,
        "ts": int(time.time()),
    })
    _persist_progress(game)

    # vitória
    if guess == game["word"]:
        training = game["mode"] == "train"
        current_streak = 0
        reward_coins = 0
        bonus_coins = 0

        if not training:
            record_termo_result(user_id, True, len(game["guesses"]))
            stats = get_termo_stats(user_id) or {}
            current_streak = int(stats.get("current_streak") or 0)

            reward_coins = _daily_coins(len(game["guesses"]))
            bonus_coins = _streak_bonus(current_streak)

            add_user_coins(user_id, reward_coins + bonus_coins)
            add_progress_xp(user_id, XP_REWARD)

        share = _share_text(game["guesses"], len(game["guesses"]), True, current_streak)
        _finish_game(game, "win", reward_coins + bonus_coins, 0 if training else XP_REWARD)

        if training:
            await update.message.reply_text(
                "🎉 <b>Você acertou no modo treino!</b>\n\n"
                f"{_history_text(game['guesses'])}\n\n"
                f"Categoria: <b>{game['category']}</b>\n"
                f"Origem: <b>{game['source']}</b>\n\n"
                f"📤 <b>Compartilhe seu resultado:</b>\n<code>{share}</code>",
                parse_mode="HTML",
                reply_markup=_share_button(share),
            )
        else:
            bonus_text = f"\n🎁 Bônus de streak: <b>+{bonus_coins} Coins</b>" if bonus_coins > 0 else ""
            await update.message.reply_text(
                "🎉 <b>Você acertou!</b>\n\n"
                f"{_history_text(game['guesses'])}\n\n"
                f"Categoria: <b>{game['category']}</b>\n"
                f"Origem: <b>{game['source']}</b>\n\n"
                f"🪙 +<b>{reward_coins}</b> Coins\n"
                f"⭐ +<b>{XP_REWARD}</b> XP"
                f"{bonus_text}\n\n"
                f"🔥 Sequência atual: <b>{current_streak} dias</b>\n\n"
                f"📤 <b>Compartilhe seu resultado:</b>\n<code>{share}</code>",
                parse_mode="HTML",
                reply_markup=_share_button(share),
            )
        return

    # derrota
    if len(game["guesses"]) >= MAX_ATTEMPTS:
        training = game["mode"] == "train"
        old_stats = get_termo_stats(user_id) or {}
        old_streak = int(old_stats.get("current_streak") or 0)

        if not training:
            record_termo_result(user_id, False, len(game["guesses"]))

        _finish_game(game, "lose")

        await update.message.reply_text(
            "❌ <b>Fim de jogo</b>\n\n"
            f"{_history_text(game['guesses'])}\n\n"
            f"Palavra correta: <b>{game['word'].upper()}</b>\n\n"
            f"Categoria: <b>{game['category']}</b>\n"
            f"Origem: <b>{game['source']}</b>"
            + ("\n\n❌ <b>Sequência perdida!</b>" if old_streak > 0 and not training else "")
            + f"\n\n📅 Próxima palavra em <b>{_next_reset_text()}</b>.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(_board_text(game), parse_mode="HTML")
