import os
import asyncio

from database import get_all_user_ids

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))


async def avisar(message, app):

    if message.from_user.id != BOT_OWNER_ID:
        return

    args = message.text.split()

    if len(args) < 3:
        await message.reply(
            "❌ Uso:\n"
            "/avisar all mensagem\n"
            "/avisar ID mensagem"
        )
        return

    target = args[1]
    text = " ".join(args[2:])

    # =================================================
    # ENVIAR PARA TODOS
    # =================================================

    if target.lower() == "all":

        users = get_all_user_ids()

        total = len(users)
        sent = 0
        failed = 0

        await message.reply(
            f"📢 Enviando aviso para {total} usuários..."
        )

        for uid in users:

            try:

                await app.send_message(
                    uid,
                    f"📢 Aviso do bot:\n\n{text}"
                )

                sent += 1

            except Exception:
                failed += 1

            await asyncio.sleep(0.05)

        await message.reply(
            "✅ Aviso enviado.\n\n"
            f"👥 Usuários encontrados: {total}\n"
            f"📨 Enviados: {sent}\n"
            f"❌ Falhas: {failed}"
        )

        return

    # =================================================
    # ENVIAR PARA UM USUÁRIO
    # =================================================

    try:

        user_id = int(target)

        await app.send_message(
            user_id,
            f"📢 Aviso do bot:\n\n{text}"
        )

        await message.reply(
            f"✅ Aviso enviado para {user_id}"
        )

    except Exception as e:

        await message.reply(
            f"❌ Falha ao enviar:\n{e}"
        )
