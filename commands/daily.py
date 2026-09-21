import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from database import create_or_get_user, claim_daily_reward, _daily_day_start_ts_sp

DAILY_COINS_MIN = 1
DAILY_COINS_MAX = 3
DAILY_GIRO_CHANCE = 0.15


def _claim_daily_sync(user_id: int, day_start_ts: int):
    create_or_get_user(int(user_id))
    return claim_daily_reward(
        user_id=int(user_id),
        day_start_ts=day_start_ts,
        coins_min=DAILY_COINS_MIN,
        coins_max=DAILY_COINS_MAX,
        giro_chance=DAILY_GIRO_CHANCE,
    )


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user_id = int(update.effective_user.id)
    day_start_ts = _daily_day_start_ts_sp()

    try:
        reward = await asyncio.to_thread(
            _claim_daily_sync,
            user_id,
            day_start_ts,
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
