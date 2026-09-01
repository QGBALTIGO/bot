from __future__ import annotations

import asyncio
import logging
import os

from telegram import Update
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from database import get_all_user_ids

logger = logging.getLogger(__name__)
MAX_BROADCAST_TEXT_LENGTH = 3500
BROADCAST_DELAY_SECONDS = 0.05


def _owner_id() -> int:
    raw = str(os.getenv("BOT_OWNER_ID", "0") or "").strip()
    if raw.isdigit():
        return int(raw)
    if raw:
        logger.error("BOT_OWNER_ID inválido; /avisar foi desativado")
    return 0


BOT_OWNER_ID = _owner_id()


def is_owner(user_id: int) -> bool:
    return BOT_OWNER_ID > 0 and int(user_id) == BOT_OWNER_ID


async def _send_notice(bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id=user_id, text=text)
        return True
    except RetryAfter as exc:
        retry_after = max(1.0, float(exc.retry_after))
        logger.warning("Flood control no broadcast; aguardando %.2fs", retry_after)
        await asyncio.sleep(retry_after)
        try:
            await bot.send_message(chat_id=user_id, text=text)
            return True
        except TelegramError:
            logger.info("Falha após retry no broadcast user_id=%s", user_id)
            return False
    except (Forbidden, BadRequest):
        # Usuário bloqueou o bot, apagou a conta ou o chat não está mais acessível.
        return False
    except TelegramError:
        logger.exception("Erro do Telegram no broadcast user_id=%s", user_id)
        return False
    except Exception:
        logger.exception("Erro inesperado no broadcast user_id=%s", user_id)
        return False


async def avisar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    if not is_owner(user.id):
        await message.reply_text("❌ Apenas o dono do bot pode usar este comando.")
        return

    if not context.args or len(context.args) < 2:
        await message.reply_html(
            "⚠️ <b>Uso correto:</b>\n"
            "<code>/avisar all sua mensagem</code>\n"
            "<code>/avisar ID_DO_USUARIO sua mensagem</code>"
        )
        return

    target = str(context.args[0] or "").strip()
    text = " ".join(context.args[1:]).strip()
    if not text:
        await message.reply_text("❌ Mensagem vazia.")
        return

    final_text = f"📢 Aviso da Source Baltigo\n\n{text}"
    if len(final_text) > MAX_BROADCAST_TEXT_LENGTH:
        await message.reply_text(
            f"❌ A mensagem é muito longa. Limite: {MAX_BROADCAST_TEXT_LENGTH} caracteres."
        )
        return

    if target.lower() == "all":
        try:
            raw_user_ids = await asyncio.to_thread(get_all_user_ids)
            user_ids = sorted(
                {
                    int(user_id)
                    for user_id in (raw_user_ids or [])
                    if str(user_id).lstrip("-").isdigit() and int(user_id) > 0
                }
            )
        except Exception:
            logger.exception("Falha ao carregar usuários para broadcast requested_by=%s", user.id)
            await message.reply_text(
                "❌ Não foi possível carregar a lista de usuários. O erro foi registrado."
            )
            return

        total = len(user_ids)
        if total == 0:
            await message.reply_text("⚠️ Nenhum usuário encontrado.")
            return

        progress = await message.reply_text(
            "📢 Iniciando envio global...\n\n"
            f"👥 Usuários encontrados: {total}"
        )

        sent = 0
        failed = 0
        for position, user_id in enumerate(user_ids, start=1):
            if await _send_notice(context.bot, user_id, final_text):
                sent += 1
            else:
                failed += 1

            if position % 250 == 0:
                try:
                    await progress.edit_text(
                        "📢 Envio global em andamento...\n\n"
                        f"📊 Processados: {position}/{total}\n"
                        f"📨 Enviados: {sent}\n"
                        f"❌ Falhas: {failed}"
                    )
                except TelegramError:
                    logger.info("Não foi possível atualizar progresso do broadcast")

            await asyncio.sleep(BROADCAST_DELAY_SECONDS)

        logger.info(
            "Broadcast concluído requested_by=%s total=%s sent=%s failed=%s",
            user.id,
            total,
            sent,
            failed,
        )
        await progress.edit_text(
            "✅ Envio finalizado.\n\n"
            f"👥 Usuários encontrados: {total}\n"
            f"📨 Enviados: {sent}\n"
            f"❌ Falhas: {failed}"
        )
        return

    try:
        target_id = int(target)
    except (TypeError, ValueError):
        await message.reply_html("❌ ID inválido. Use <code>all</code> ou um ID numérico.")
        return

    if target_id <= 0:
        await message.reply_text("❌ ID inválido.")
        return

    if await _send_notice(context.bot, target_id, final_text):
        logger.info("Aviso individual enviado target=%s requested_by=%s", target_id, user.id)
        await message.reply_html(
            f"✅ Aviso enviado para o usuário <code>{target_id}</code>."
        )
    else:
        await message.reply_html(
            f"❌ Não foi possível enviar o aviso para <code>{target_id}</code>."
        )
