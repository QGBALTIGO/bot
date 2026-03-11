import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import (
    block_user_messages,
    enqueue_user_message,
    fail_user_message,
    get_message_settings,
    get_profile_settings_by_nickname,
    has_accepted_terms,
    mark_user_message_delivered,
    report_user_message,
    set_message_allow_anonymous,
    set_message_allow_messages,
    unblock_user_messages,
)
from utils.gatekeeper import TERMS_VERSION


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


async def _ensure_gatekeeper(update: Update) -> bool:
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return False

    if not has_accepted_terms(user.id, TERMS_VERSION):
        await message.reply_text(
            "📜 <b>Antes de usar este recurso</b>\n\n"
            "Você precisa aceitar os termos do bot primeiro.\n"
            "Use <code>/start</code> para continuar.",
            parse_mode=ParseMode.HTML,
        )
        return False

    return True


def _reply_error_text(error_code: str, extra: dict | None = None) -> str:
    extra = extra or {}

    if error_code == "target_nickname_required":
        return "❌ <b>Nickname não informado</b>\n\nEscolha para quem deseja enviar a mensagem."
    if error_code == "empty_message":
        return "❌ <b>Mensagem vazia</b>\n\nEscreva algo antes de enviar."
    if error_code == "message_too_long":
        return "❌ <b>Mensagem muito longa</b>\n\nO limite é de 500 caracteres."
    if error_code == "sender_no_nickname":
        return "🏷️ <b>Defina seu nickname primeiro</b>\n\nVocê precisa ter um nickname para usar o sistema de mensagens."
    if error_code == "target_not_found":
        return "🔎 <b>Nickname não encontrado</b>\n\nConfira o nickname digitado e tente novamente."
    if error_code == "cannot_message_self":
        return "🙃 <b>Não dá para enviar para você mesmo</b>\n\nEscolha outro jogador."
    if error_code == "target_messages_disabled":
        return "🔒 <b>Mensagens indisponíveis</b>\n\nEsse jogador não está aceitando mensagens no momento."
    if error_code == "target_anonymous_disabled":
        return "👤 <b>Anônimas desativadas</b>\n\nEsse jogador não aceita mensagens anônimas."
    if error_code == "blocked_by_target":
        return "🚫 <b>Envio bloqueado</b>\n\nVocê não pode enviar mensagens para esse jogador."
    if error_code == "you_blocked_target":
        return "🚫 <b>Jogador bloqueado</b>\n\nVocê bloqueou esse jogador. Desbloqueie antes de enviar."
    if error_code == "insufficient_coins":
        return f"💰 <b>Coins insuficientes</b>\n\nVocê precisa de <b>{MSG_ANON_COST} coins</b> para enviar uma mensagem anônima."
    if error_code == "cooldown_active":
        remaining = int(extra.get("remaining_seconds") or 0)
        return f"⏳ <b>Aguarde um pouco</b>\n\nVocê poderá enviar outra mensagem em <b>{remaining}s</b>."
    if error_code == "sender_not_found":
        return "❌ <b>Conta não encontrada</b>\n\nUse <code>/start</code> e tente novamente."

    return "❌ <b>Não foi possível enviar a mensagem</b>\n\nTente novamente em instantes."


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

    if not await _ensure_gatekeeper(update):
        return

    relay_id = _relay_chat_id()
    if not relay_id:
        await message.reply_text(
            "📡 <b>Sistema indisponível</b>\n\n"
            "O canal de relay não está configurado no momento.",
            parse_mode=ParseMode.HTML,
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
        await message.reply_text(
            _reply_error_text(result.get("error", ""), result),
            parse_mode=ParseMode.HTML,
        )
        return

    msg_row = result["message"]
    message_id = int(msg_row["message_id"])
    to_user_id = int(result["to_user_id"])
    from_nickname = result["from_nickname"]
    to_nickname = result["to_nickname"]

    relay_text = (
        "📨 <b>Relay de Mensagem</b>\n\n"
        f"🆔 <b>ID:</b> <code>#{message_id}</code>\n"
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
            "📡 <b>Canal de entrega indisponível</b>\n\n"
            "Sua mensagem não pôde passar pelo canal do sistema.\n"
            "Nada foi cobrado permanentemente.",
            parse_mode=ParseMode.HTML,
        )
        return

    if is_anonymous:
        receiver_text = (
            "👤 <b>Nova Mensagem Anônima</b>\n\n"
            f"🆔 <b>ID:</b> <code>#{message_id}</code>\n"
            f"💬 <b>Mensagem:</b>\n{text}\n\n"
            "🚨 <b>Denunciar</b>\n"
            f"<code>/denunciarmsg {message_id} motivo</code>"
        )
    else:
        receiver_text = (
            "💬 <b>Nova Mensagem</b>\n\n"
            f"🆔 <b>ID:</b> <code>#{message_id}</code>\n"
            f"👤 <b>De:</b> {from_nickname}\n"
            f"💬 <b>Mensagem:</b>\n{text}\n\n"
           "📖 <b>Ajuda</b>\n"
"Use <code>/msgtutorial</code> para ver como responder, bloquear, configurar e denunciar mensagens."
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
            "📭 <b>Entrega não concluída</b>\n\n"
            "A mensagem não pôde ser entregue ao destinatário.\n"
            "Nada foi cobrado permanentemente.",
            parse_mode=ParseMode.HTML,
        )
        return

    mark_user_message_delivered(message_id)

    if is_anonymous:
        await message.reply_text(
            "👤 <b>Mensagem anônima enviada</b>\n\n"
            f"Destinatário: <b>{to_nickname}</b>\n"
            f"Custo: <b>{MSG_ANON_COST} coins</b>\n"
            f"ID da mensagem: <code>#{message_id}</code>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.reply_text(
            "💬 <b>Mensagem enviada</b>\n\n"
            f"Destinatário: <b>{to_nickname}</b>\n"
            f"ID da mensagem: <code>#{message_id}</code>",
            parse_mode=ParseMode.HTML,
        )


async def msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    if not await _ensure_gatekeeper(update):
        return

    parts = message.text.split(maxsplit=2) if message.text else []
    if len(parts) < 3:
        await message.reply_text(
            "💬 <b>Como enviar uma mensagem</b>\n\n"
            "Use:\n"
            "<code>/msg nickname mensagem</code>\n\n"
            "Exemplo:\n"
            "<code>/msg baltigo oi, vi sua coleção</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await _deliver_message(update, context, parts[1].strip(), parts[2].strip(), False)


async def msganon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    if not await _ensure_gatekeeper(update):
        return

    parts = message.text.split(maxsplit=2) if message.text else []
    if len(parts) < 3:
        await message.reply_text(
            "👤 <b>Como enviar uma mensagem anônima</b>\n\n"
            "Use:\n"
            "<code>/msganon nickname mensagem</code>\n\n"
            f"Custo: <b>{MSG_ANON_COST} coins</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    await _deliver_message(update, context, parts[1].strip(), parts[2].strip(), True)


async def bloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not await _ensure_gatekeeper(update):
        return

    if not context.args:
        await message.reply_text(
            "🚫 <b>Como bloquear um jogador</b>\n\n"
            "Use:\n<code>/bloquearmsg nickname</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_nickname = context.args[0].strip()
    target = get_profile_settings_by_nickname(target_nickname)

    if not target:
        await message.reply_text(
            "🔎 <b>Nickname não encontrado</b>\n\n"
            "Confira o nickname digitado e tente novamente.",
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id = int(target["user_id"])

    if target_user_id == sender.id:
        await message.reply_text(
            "🙃 <b>Ação inválida</b>\n\n"
            "Você não pode bloquear a si mesmo.",
            parse_mode=ParseMode.HTML,
        )
        return

    block_user_messages(sender.id, target_user_id)
    await message.reply_text(
        "🚫 <b>Jogador bloqueado</b>\n\n"
        f"Você não receberá mais mensagens de <b>{target_nickname}</b>.",
        parse_mode=ParseMode.HTML,
    )


async def desbloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not await _ensure_gatekeeper(update):
        return

    if not context.args:
        await message.reply_text(
            "✅ <b>Como desbloquear um jogador</b>\n\n"
            "Use:\n<code>/desbloquearmsg nickname</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_nickname = context.args[0].strip()
    target = get_profile_settings_by_nickname(target_nickname)

    if not target:
        await message.reply_text(
            "🔎 <b>Nickname não encontrado</b>\n\n"
            "Confira o nickname digitado e tente novamente.",
            parse_mode=ParseMode.HTML,
        )
        return

    target_user_id = int(target["user_id"])

    unblock_user_messages(sender.id, target_user_id)
    await message.reply_text(
        "✅ <b>Jogador desbloqueado</b>\n\n"
        f"Você poderá receber mensagens de <b>{target_nickname}</b> novamente.",
        parse_mode=ParseMode.HTML,
    )


async def msgconfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not await _ensure_gatekeeper(update):
        return

    if not context.args:
        settings = get_message_settings(sender.id)
        await message.reply_text(
            "⚙️ <b>Configurações de Mensagens</b>\n\n"
            f"💬 Mensagens normais: <b>{'Ativadas' if settings.get('allow_messages', True) else 'Desativadas'}</b>\n"
            f"👤 Mensagens anônimas: <b>{'Ativadas' if settings.get('allow_anonymous', True) else 'Desativadas'}</b>\n\n"
            "Comandos disponíveis:\n"
            "<code>/msgconfig on</code>\n"
            "<code>/msgconfig off</code>\n"
            "<code>/msgconfig anon on</code>\n"
            "<code>/msgconfig anon off</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = [p.strip().lower() for p in context.args]

    if len(parts) == 1 and parts[0] in ("on", "off"):
        set_message_allow_messages(sender.id, parts[0] == "on")
        await message.reply_text(
            f"⚙️ <b>Mensagens {'ativadas' if parts[0] == 'on' else 'desativadas'}</b>\n\n"
            "Sua preferência foi atualizada com sucesso.",
            parse_mode=ParseMode.HTML,
        )
        return

    if len(parts) == 2 and parts[0] == "anon" and parts[1] in ("on", "off"):
        set_message_allow_anonymous(sender.id, parts[1] == "on")
        await message.reply_text(
            f"👤 <b>Mensagens anônimas {'ativadas' if parts[1] == 'on' else 'desativadas'}</b>\n\n"
            "Sua preferência foi atualizada com sucesso.",
            parse_mode=ParseMode.HTML,
        )
        return

    await message.reply_text(
        "⚠️ <b>Uso correto</b>\n\n"
        "<code>/msgconfig</code>\n"
        "<code>/msgconfig on</code>\n"
        "<code>/msgconfig off</code>\n"
        "<code>/msgconfig anon on</code>\n"
        "<code>/msgconfig anon off</code>",
        parse_mode=ParseMode.HTML,
    )


async def denunciarmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    sender = update.effective_user

    if not message or not sender:
        return

    if not await _ensure_gatekeeper(update):
        return

    if not context.args:
        await message.reply_text(
            "🚨 <b>Como denunciar uma mensagem</b>\n\n"
            "Use:\n<code>/denunciarmsg ID motivo</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        message_id = int(context.args[0])
    except ValueError:
        await message.reply_text(
            "❌ <b>ID inválido</b>\n\n"
            "Informe um ID de mensagem válido.",
            parse_mode=ParseMode.HTML,
        )
        return

    reason = " ".join(context.args[1:]).strip()
    result = report_user_message(sender.id, message_id, reason)

    if not result.get("ok"):
        await message.reply_text(
            "📭 <b>Mensagem não encontrada</b>\n\n"
            "Esse ID não está na sua caixa de mensagens.",
            parse_mode=ParseMode.HTML,
        )
        return

    await message.reply_text(
        "🚨 <b>Denúncia enviada</b>\n\n"
        "A mensagem foi marcada para análise.",
        parse_mode=ParseMode.HTML,
    )
