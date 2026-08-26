from __future__ import annotations

import html
import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry
from ecosystem_repository import push_notification
from identity_repository import find_identity_by_nickname
from messages_repository import (
    MessageError,
    fail_message_and_refund,
    get_message_settings,
    mark_message_delivered,
    prepare_message,
    report_message,
    set_message_block,
    update_message_settings,
)
from system_events import emit_event
from utils.gatekeeper import gatekeeper
from utils.runtime_guard import rate_limiter

MSG_ANON_COST = max(0, int(os.getenv("MSG_ANON_COST", "3")))
MSG_COOLDOWN_NORMAL_SECONDS = max(5, int(os.getenv("MSG_COOLDOWN_NORMAL_SECONDS", "30")))
MSG_COOLDOWN_ANON_SECONDS = max(10, int(os.getenv("MSG_COOLDOWN_ANON_SECONDS", "90")))
MESSAGE_RELAY_CHANNEL_ID = os.getenv("MESSAGE_RELAY_CHANNEL_ID", "").strip()


async def _gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg = update.effective_message
    ok, blocked = await gatekeeper(update, context)
    if not ok and blocked and msg:
        await msg.reply_html(blocked)
    return ok


def _error_text(exc: MessageError) -> str:
    if exc.code == "cooldown_active":
        return f"⏳ Aguarde <b>{int(exc.extra.get('remaining_seconds') or 1)}s</b> antes de enviar outra mensagem."
    return f"⚠️ {html.escape(exc.message, quote=False)}"


async def _audit_relay(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not MESSAGE_RELAY_CHANNEL_ID:
        return
    chat_id = int(MESSAGE_RELAY_CHANNEL_ID) if MESSAGE_RELAY_CHANNEL_ID.lstrip("-").isdigit() else MESSAGE_RELAY_CHANNEL_ID
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        return


async def _deliver(update: Update, context: ContextTypes.DEFAULT_TYPE, nickname: str, text: str, anonymous: bool) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not await _gate(update, context):
        return
    if not await rate_limiter.allow(f"messages:cmd:{int(user.id)}", limit=8, window_seconds=60):
        await msg.reply_text("⌛ Você está enviando mensagens rápido demais.")
        return
    try:
        prepared = prepare_message(
            int(user.id), nickname, text, is_anonymous=anonymous, anon_cost=MSG_ANON_COST,
            normal_cooldown_seconds=MSG_COOLDOWN_NORMAL_SECONDS,
            anonymous_cooldown_seconds=MSG_COOLDOWN_ANON_SECONDS,
        )
    except MessageError as exc:
        await msg.reply_html(_error_text(exc))
        return

    row = prepared["message"]
    mid = int(row["message_id"])
    target = int(prepared["to_user_id"])
    safe_text = html.escape(str(row.get("message_text") or ""), quote=False)
    if anonymous:
        receiver = (
            f"👤 <b>Nova mensagem anônima</b>\n\n"
            f"🆔 <code>#{mid}</code>\n💬 {safe_text}\n\n"
            f"🚨 Denunciar: <code>/denunciarmsg {mid} motivo</code>\n"
            "⚙️ Controle mensagens anônimas em <code>/mensagens</code>."
        )
    else:
        sender = html.escape(str(prepared.get("from_nickname") or "Jogador"), quote=False)
        receiver = (
            f"💬 <b>Nova mensagem</b>\n\n"
            f"🆔 <code>#{mid}</code>\n👤 De: <b>{sender}</b>\n💬 {safe_text}\n\n"
            f"↩️ Responder: <code>/msg {sender} sua mensagem</code>\n"
            "📥 Histórico e privacidade: <code>/mensagens</code>."
        )
    try:
        await context.bot.send_message(chat_id=target, text=receiver, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as exc:
        fail_message_and_refund(mid, f"delivery_failed:{type(exc).__name__}")
        await msg.reply_text("📭 Não consegui entregar. Se havia cobrança anônima, ela foi devolvida automaticamente.")
        return

    mark_message_delivered(mid)
    emit_event(int(user.id), "message_sent", label=f"💬 Mensagem enviada para {prepared.get('to_nickname') or 'jogador'}", metadata={"message_id": mid, "anonymous": anonymous})
    emit_event(int(user.id), "social_interaction", label="💬 Interação por mensagem", metadata={"message_id": mid})
    push_notification(
        target,
        "messages",
        "👤 Nova mensagem anônima" if anonymous else f"💬 Nova mensagem de {prepared.get('from_nickname') or 'um jogador'}",
        str(row.get("message_text") or "")[:260],
        "/messages",
        {"message_id": mid, "anonymous": anonymous},
    )
    await _audit_relay(
        context,
        f"📨 <b>Mensagem V2 entregue</b>\nID: <code>#{mid}</code>\nDe: <code>{int(user.id)}</code>\nPara: <code>{target}</code>\nAnônima: {'sim' if anonymous else 'não'}\nTexto: {safe_text}",
    )
    await msg.reply_html(
        f"✅ <b>Mensagem enviada</b>\n\n🎯 Para: <b>{html.escape(str(prepared.get('to_nickname') or nickname), quote=False)}</b>\n🆔 <code>#{mid}</code>"
        + (f"\n💰 Custo: <b>{MSG_ANON_COST} coins</b>" if anonymous else "\n💰 Custo: <b>grátis</b>")
    )


async def msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.reply_html("💬 <b>Enviar mensagem</b>\n\n<code>/msg nickname sua mensagem</code>")
        return
    await _deliver(update, context, parts[1], parts[2], False)


async def msganon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.reply_html(f"👤 <b>Mensagem anônima</b>\n\n<code>/msganon nickname mensagem</code>\n💰 Custo: <b>{MSG_ANON_COST} coins</b>")
        return
    await _deliver(update, context, parts[1], parts[2], True)


async def bloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user or not await _gate(update, context): return
    if not context.args: await message.reply_html("🚫 <b>Bloquear</b>\n\n<code>/bloquearmsg nickname</code>"); return
    target = find_identity_by_nickname(context.args[0])
    if not target: await message.reply_text("🔎 Nickname não encontrado."); return
    try: set_message_block(int(user.id), int(target["user_id"]), True)
    except MessageError as exc: await message.reply_html(_error_text(exc)); return
    await message.reply_text("🚫 Jogador bloqueado para mensagens.")


async def desbloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user or not await _gate(update, context): return
    if not context.args: await message.reply_html("✅ <b>Desbloquear</b>\n\n<code>/desbloquearmsg nickname</code>"); return
    target = find_identity_by_nickname(context.args[0])
    if not target: await message.reply_text("🔎 Nickname não encontrado."); return
    set_message_block(int(user.id), int(target["user_id"]), False)
    await message.reply_text("✅ Jogador desbloqueado.")


async def msgconfig(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user or not await _gate(update, context): return
    args = [x.lower() for x in context.args]
    if not args:
        s = get_message_settings(int(user.id))
        await message.reply_html(
            f"⚙️ <b>Privacidade de mensagens</b>\n\n💬 Normais: <b>{'ativadas' if s['allow_messages'] else 'desativadas'}</b>\n👤 Anônimas: <b>{'ativadas' if s['allow_anonymous'] else 'desativadas'}</b>\n\nAbra <code>/mensagens</code> para controlar visualmente."
        ); return
    if len(args) == 1 and args[0] in {'on','off'}:
        update_message_settings(int(user.id), allow_messages=args[0] == 'on')
    elif len(args) == 2 and args[0] == 'anon' and args[1] in {'on','off'}:
        update_message_settings(int(user.id), allow_anonymous=args[1] == 'on')
    else:
        await message.reply_text("⚠️ Configuração inválida."); return
    await message.reply_text("✅ Preferência atualizada.")


async def denunciarmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if not message or not user or not await _gate(update, context): return
    if not context.args or not context.args[0].isdigit(): await message.reply_html("🚨 <b>Denunciar</b>\n\n<code>/denunciarmsg ID motivo</code>"); return
    try: report_message(int(user.id), int(context.args[0]), " ".join(context.args[1:]).strip())
    except MessageError as exc: await message.reply_html(_error_text(exc)); return
    await message.reply_text("🚨 Denúncia registrada para moderação.")


async def msgtutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not await _gate(update, context): return
    await message.reply_html(
        "💬 <b>Mensagens Baltigo</b>\n\n"
        "<code>/msg nickname texto</code> — grátis\n"
        f"<code>/msganon nickname texto</code> — {MSG_ANON_COST} coins\n"
        "<code>/mensagens</code> — caixa de entrada, enviados, privacidade e bloqueios\n"
        "<code>/denunciarmsg ID motivo</code> — moderação\n\n"
        "Mensagens anônimas escondem o remetente do destinatário, mas preservam a origem para segurança e moderação."
    )


async def mensagens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update, context,
        WebAppEntry(title="Central de Mensagens", description="Histórico, privacidade, bloqueios e denúncias no mesmo padrão social do Baltigo.", button="💬 Abrir Mensagens", path="/messages", icon="💬"),
    )
