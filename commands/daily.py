from telegram import Update
from telegram.ext import ContextTypes

from database import create_or_get_user, claim_daily_reward, _daily_day_start_ts_sp

DAILY_COINS_MIN = 1
DAILY_COINS_MAX = 3
DAILY_GIRO_CHANCE = 0.15


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    create_or_get_user(user_id)

    day_start_ts = _daily_day_start_ts_sp()

    try:
        reward = claim_daily_reward(
            user_id=user_id,
            day_start_ts=day_start_ts,
            coins_min=DAILY_COINS_MIN,
            coins_max=DAILY_COINS_MAX,
            giro_chance=DAILY_GIRO_CHANCE,
        )
    except Exception as e:
        print("DAILY ERROR:", e)
        await update.message.reply_html(
            "⚠️ Não consegui resgatar agora. Tente novamente."
        )
        return

    if not reward:
        await update.message.reply_html(
            "📦 <b>DAILY</b>\n\n"
            "Você já resgatou hoje.\n"
            "Volte amanhã 🙂"
        )
        return

    if reward["type"] == "giro":
        await update.message.reply_html(
            "📦 <b>DAILY</b>\n\n"
            "✅ Você recebeu: <b>+1 giro</b> 🎡"
        )
    else:
        await update.message.reply_html(
            "📦 <b>DAILY</b>\n\n"
            f"✅ Você recebeu: <b>+{int(reward['amount'])} coins</b> 🪙"
        )
