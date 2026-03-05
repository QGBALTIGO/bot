from telegram import Update
from telegram.ext import ContextTypes
from database import create_or_get_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    create_or_get_user(user_id)

    name = update.effective_user.first_name

    message = f"""
Olá {name}! 🤖

⚠️ IMPORTANTE

Para continuar utilizando o bot você precisa
ler e aceitar nossos Termos de Uso e Política
de Privacidade.

Clique no botão abaixo para continuar.
"""

    await update.message.reply_text(message)
