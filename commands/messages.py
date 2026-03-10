import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import (
    block_user_messages,
    enqueue_user_message,
    fail_user_message,
    get_message_settings,
    get_profile_settings,
    get_profile_settings_by_nickname,
    mark_user_message_delivered,
    report_user_message,
    set_message_allow_anonymous,
    set_message_allow_messages,
    unblock_user_messages,
)


MESSAGE_RELAY_CHANNEL_ID_RAW = os.getenv("MESSAGE_RELAY_CHANNEL_ID", "").strip()
MSG_ANON_COST = int(os.getenv("MSG_ANON_COST", "3"))
MSG_COOLDOWN_NORMAL_SECONDS = int(os.getenv("MSG_COOLDOWN_NORMAL_SECONDS", "30"))
MSG_COOLDOWN_ANON_SECONDS = int(os.getenv("MSG_COOLDOWN_ANON_SECONDS", "90"))


def _relay_chat_id():
    raw = MESSAGE_RELAY_CHANNEL_ID_RAW.strip()
    if not raw:
        return None

    clean = raw.replace(" ", "")
    if clean.lstrip("-").isdigit():
        return int(clean)
    return clean


def _reply_error_text(error_code: str, extra: dict | None = None) -> str:
    extra = extra or {}

    if error_code == "target_nickname_required":
        return "❌ Você precisa informar um nickname."
    if error_code == "empty_message":
        return "❌ Mensagem vazia."
    if error_code == "message_too_long":
        return "❌ A mensagem pode ter no máximo 500 caracteres."
    if error_code == "sender_no_nickname":
        return "❌ Você precisa definir um nickname antes de usar mensagens."
    if error_code == "target_not_found":
        return "❌ Nickname não encontrado."
    if error_code == "cannot_message_self":
        return "❌ Você não pode enviar mensagem para si mesmo."
    if error_code == "target_messages_disabled":
        return "❌ Esse jogador não está aceitando mensagens."
    if error_code == "target_anonymous_disabled":
        return "❌ Esse jogador não aceita mensagens anônimas."
    if error_code == "blocked_by_target":
        return "❌ Você não pode enviar mensagens para esse jogador."
    if error_code == "you_blocked_target":
        return "❌ Você bloqueou esse jogador. Desbloqueie antes de enviar."
    if error_code == "insufficient_coins":
        return f"❌ Você precisa de {MSG_ANON_COST} coins para enviar uma mensagem anônima."
    if error_code == "cooldown_active":
        remaining = int(extra.get("remaining_seconds") or 0)
        return f"⏳ Aguarde {remaining}s para enviar outra mensagem."

    return "❌ Não foi possível enviar a mensagem."


async def _send_relay_log(context: ContextTypes.DEFAULT_TYPE, payload: str):
    relay_id = _relay_chat_id()
    if not relay_id:
        raise RuntimeError("MESSAGE_RELAY_CHANNEL_ID não configurado.")

    await context.bot.send_message(
        chat_id=relay_id,
        text=payload,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def _deliver_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target_nickname: str,
    text: str,
    is_anonymous: bool,
):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    relay_id = _relay_chat_id()
    if not relay_id:
        await message.reply_text(
            "⚠️ Sistema de mensagens indisponível no momento.\n"
            "Canal de relay não configurado."
        )
        return

    result = enqueue_user_message(
        from_user_id=sender.id,
        target_nickname=target_nickname,
        message_text=text,
        is_anonymous=is_anonymous,
        anon_cost=MSG_ANON_COST,
        normal_cooldown_seconds=MSG_COOLDOWN_NORMAL_SECONDS,
        anonymous_cooldown_seconds=MSG_COOLDOWN_ANON_SECONDS,
    )

    if not result.get("ok"):
        await message.reply_text(_reply_error_text(result.get("error", ""), result))
        return

    msg_row = result["message"]
    message_id = int(msg_row["message_id"])
    to_user_id = int(result["to_user_id"])
    from_nickname = result["from_nickname"]
    to_nickname = result["to_nickname"]

    relay_text = (
        "📨 <b>Relay de mensagem</b>\n\n"
        f"🆔 <b>Mensagem:</b> #{message_id}\n"
        f"👤 <b>De:</b> {from_nickname} (<code>{sender.id}</code>)\n"
        f"🎯 <b>Para:</b> {to_nickname} (<code>{to_user_id}</code>)\n"
        f"🕵️ <b>Anônima:</b> {'Sim' if is_anonymous else 'Não'}\n"
        f"💰 <b>Custo:</b> {MSG_ANON_COST if is_anonymous else 0}\n\n"
        f"💬 <b>Texto:</b>\n{text}"
    )

    try:
        await _send_relay_log(context, relay_text)
    except Exception as e:
        fail_user_message(message_id, f"relay_failed: {e}")
        await message.reply_text(
            "❌ Não foi possível passar a mensagem pelo canal de relay.\n"
            "Nada foi cobrado permanentemente."
        )
        return

    if is_anonymous:
        receiver_text = (
            "👤 <b>Nova mensagem anônima</b>\n\n"
            f"🆔 <b>ID:</b> #{message_id}\n"
            f"💬 <b>Mensagem:</b>\n{text}\n\n"
            "🚨 Se necessário, denuncie com:\n"
            f"<code>/denunciarmsg {message_id} motivo</code>"
        )
    else:
        receiver_text = (
            "💬 <b>Nova mensagem</b>\n\n"
            f"🆔 <b>ID:</b> #{message_id}\n"
            f"👤 <b>De:</b> {from_nickname}\n"
            f"💬 <b>Mensagem:</b>\n{text}\n\n"
            "🚨 Se necessário, denuncie com:\n"
            f"<code>/denunciarmsg {message_id} motivo</code>"
        )

    try:
        await context.bot.send_message(
            chat_id=to_user_id,
            text=receiver_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        fail_user_message(message_id, f"delivery_failed: {e}")
        await message.reply_text(
            "❌ Falha ao entregar a mensagem ao destinatário.\n"
            "Nada foi cobrado permanentemente."
        )
        return

    mark_user_message_delivered(message_id)

    if is_anonymous:
        await message.reply_text(
            f"✅ Mensagem anônima enviada para {to_nickname}.\n"
            f"💰 Custo: {MSG_ANON_COST} coins\n"
            f"🆔 ID: #{message_id}"
        )
    else:
        await message.reply_text(
            f"✅ Mensagem enviada para {to_nickname}.\n"
            f"🆔 ID: #{message_id}"
        )


async def msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    parts = message.text.split(maxsplit=2) if message.text else []
    if len(parts) < 3:
        await message.reply_text(
            "⚠️ Uso correto:\n"
            "/msg nickname mensagem"
        )
        return

    target_nickname = parts[1].strip()
    text = parts[2].strip()

    await _deliver_message(update, context, target_nickname, text, False)


async def msganon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    parts = message.text.split(maxsplit=2) if message.text else []
    if len(parts) < 3:
        await message.reply_text(
            "⚠️ Uso correto:\n"
            "/msganon nickname mensagem"
        )
        return

    target_nickname = parts[1].strip()
    text = parts[2].strip()

    await _deliver_message(update, context, target_nickname, text, True)


async def bloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not context.args:
        await message.reply_text("⚠️ Uso correto:\n/bloquearmsg nickname")
        return

    target_nickname = context.args[0].strip()
    target = get_profile_settings_by_nickname(target_nickname)

    if not target:
        await message.reply_text("❌ Nickname não encontrado.")
        return

    target_user_id = int(target["user_id"])

    if target_user_id == sender.id:
        await message.reply_text("❌ Você não pode bloquear a si mesmo.")
        return

    block_user_messages(sender.id, target_user_id)
    await message.reply_text(f"🚫 Você bloqueou {target_nickname} para mensagens.")


async def desbloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not context.args:
        await message.reply_text("⚠️ Uso correto:\n/desbloquearmsg nickname")
        return

    target_nickname = context.args[0].strip()
    target = get_profile_settings_by_nickname(target_nickname)

    if not target:
        await message.reply_text("❌ Nickname não encontrado.")
        return

    target_user_id = int(target["user_id"])

    unblock_user_messages(sender.id, target_user_id)
    await message.reply_text(f"✅ {target_nickname} foi desbloqueado para mensagens.")


async def msgconfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not context.args:
        settings = get_message_settings(sender.id)
        await message.reply_text(
            "⚙️ Configuração de mensagens\n\n"
            f"💬 Receber mensagens: {'ON' if settings.get('allow_messages', True) else 'OFF'}\n"
            f"👤 Receber anônimas: {'ON' if settings.get('allow_anonymous', True) else 'OFF'}\n\n"
            "Use:\n"
            "/msgconfig on\n"
            "/msgconfig off\n"
            "/msgconfig anon on\n"
            "/msgconfig anon off"
        )
        return

    parts = [p.strip().lower() for p in context.args]

    if len(parts) == 1 and parts[0] in ("on", "off"):
        set_message_allow_messages(sender.id, parts[0] == "on")
        await message.reply_text(
            f"✅ Recebimento de mensagens {'ativado' if parts[0] == 'on' else 'desativado'}."
        )
        return

    if len(parts) == 2 and parts[0] == "anon" and parts[1] in ("on", "off"):
        set_message_allow_anonymous(sender.id, parts[1] == "on")
        await message.reply_text(
            f"✅ Recebimento de mensagens anônimas {'ativado' if parts[1] == 'on' else 'desativado'}."
        )
        return

    await message.reply_text(
        "⚠️ Uso correto:\n"
        "/msgconfig\n"
        "/msgconfig on\n"
        "/msgconfig off\n"
        "/msgconfig anon on\n"
        "/msgconfig anon off"
    )


async def denunciarmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not context.args:
        await message.reply_text(
            "⚠️ Uso correto:\n"
            "/denunciarmsg ID motivo"
        )
        return

    try:
        message_id = int(context.args[0])
    except ValueError:
        await message.reply_text("❌ ID inválido.")
        return

    reason = " ".join(context.args[1:]).strip()

    result = report_user_message(sender.id, message_id, reason)

    if not result.get("ok"):
        await message.reply_text("❌ Mensagem não encontrada na sua caixa.")
        return

    await message.reply_text("🚨 Mensagem denunciada com sucesso.")
