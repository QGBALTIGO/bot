# ADICIONA ESSES IMPORTS NO TOPO
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}"


# =========================
# BLOQUEIO GLOBAL PV
# =========================
def _only_private(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == ChatType.PRIVATE)


async def _block_group_message(update: Update):
    msg = update.effective_message
    if not msg:
        return

    texto = (
        "🎌 <b>TERMO ANIME</b>\n\n"
        "Esse jogo funciona apenas no <b>privado</b> do bot.\n\n"
        "Jogue sem bagunça, com tempo e ranking só seu 👑"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 Jogar no privado", url=BOT_PRIVATE_URL)]
    ])

    await msg.reply_text(texto, parse_mode="HTML", reply_markup=kb)


# =========================================================
# COMMAND HANDLERS
# =========================================================

async def termo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not _only_private(update):
        await _block_group_message(update)
        return

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

    if not _only_private(update):
        await _block_group_message(update)
        return

    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _stats_text(int(update.effective_user.id)),
        parse_mode="HTML",
    )


async def termo_ranking_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not _only_private(update):
        await _block_group_message(update)
        return

    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_global_ranking(10), "Ranking Termo Anime"),
        parse_mode="HTML",
    )


async def termo_ranking_week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not _only_private(update):
        await _block_group_message(update)
        return

    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(7, 10), "Ranking Termo — Semana"),
        parse_mode="HTML",
    )


async def termo_ranking_month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not _only_private(update):
        await _block_group_message(update)
        return

    if not await _gatekeeper_ok(update):
        return

    await update.message.reply_text(
        _ranking_text(get_termo_period_ranking(30, 10), "Ranking Termo — Mês"),
        parse_mode="HTML",
    )


async def termo_treino_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not _only_private(update):
        await _block_group_message(update)
        return

    if not await _gatekeeper_ok(update):
        return

    await _start_train(update, use_edit=False)


async def termo_treino_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not _only_private(update):
        await _block_group_message(update)
        return

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

    if not _only_private(update):
        await _block_group_message(update)
        return

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

    if not _only_private(update):
        return

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

    if not _only_private(update):
        return

    if not update.message or not update.message.text or not update.effective_user:
        return

    _touch_identity_from_update(update)

    if not has_accepted_terms(int(update.effective_user.id), TERMS_VERSION):
        return

    # resto do código continua igual...
