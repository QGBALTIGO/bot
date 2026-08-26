from __future__ import annotations

import html
import os

from telegram import Update
from telegram.ext import ContextTypes

from commands.v2_entry import WebAppEntry, open_webapp_entry
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
from utils.gatekeeper import gatekeeper
from utils.runtime_guard import rate_limiter


MSG_ANON_COST = max(0, int(os.getenv("MSG_ANON_COST", "3")))
MSG_COOLDOWN_NORMAL_SECONDS = max(5, int(os.getenv("MSG_COOLDOWN_NORMAL_SECONDS", "30")))
MSG_COOLDOWN_ANON_SECONDS = max(10, int(os.getenv("MSG_COOLDOWN_ANON_SECONDS", "90")))
MESSAGE_RELAY_CHANNEL_ID = os.getenv("MESSAGE_RELAY_CHANNEL_ID", "").strip()


async def _gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    msg=update.effective_message
    ok, blocked=await gatekeeper(update,context)
    if not ok and blocked and msg: await msg.reply_html(blocked)
    return ok


def _error_text(exc: MessageError) -> str:
    if exc.code == "cooldown_active":
        return f"⏳ Aguarde <b>{int(exc.extra.get('remaining_seconds') or 1)}s</b> antes de enviar outra mensagem."
    return f"⚠️ {html.escape(exc.message, quote=False)}"


async def _audit_relay(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    raw=MESSAGE_RELAY_CHANNEL_ID
    if not raw: return
    chat_id=int(raw) if raw.lstrip('-').isdigit() else raw
    try:
        await context.bot.send_message(chat_id=chat_id,text=text,parse_mode="HTML",disable_web_page_preview=True)
    except Exception:
        # Relay is an audit convenience, never a delivery dependency.
        return


async def _deliver(update: Update, context: ContextTypes.DEFAULT_TYPE, nickname: str, text: str, anonymous: bool) -> None:
    msg=update.effective_message; user=update.effective_user
    if not msg or not user or not await _gate(update,context): return
    if not await rate_limiter.allow(f"messages:cmd:{int(user.id)}",limit=8,window_seconds=60):
        await msg.reply_text("⌛ Você está enviando comandos de mensagem rápido demais."); return
    try:
        prepared=prepare_message(
            int(user.id),nickname,text,is_anonymous=anonymous,anon_cost=MSG_ANON_COST,
            normal_cooldown_seconds=MSG_COOLDOWN_NORMAL_SECONDS,
            anonymous_cooldown_seconds=MSG_COOLDOWN_ANON_SECONDS,
        )
    except MessageError as exc:
        await msg.reply_html(_error_text(exc)); return

    row=prepared["message"]; mid=int(row["message_id"]); target=int(prepared["to_user_id"])
    safe_text=html.escape(str(row.get("message_text") or ""),quote=False)
    if anonymous:
        receiver=(f"👤 <b>Nova mensagem anônima</b>\n\n🆔 <code>#{mid}</code>\n💬 {safe_text}\n\n"
                  f"Para denunciar: <code>/denunciarmsg {mid} motivo</code>")
    else:
        sender=html.escape(str(prepared.get("from_nickname") or "Jogador"),quote=False)
        receiver=(f"💬 <b>Nova mensagem</b>\n\n🆔 <code>#{mid}</code>\n👤 De: <b>{sender}</b>\n💬 {safe_text}\n\n"
                  f"Responda com <code>/msg {sender} sua mensagem</code>")
    try:
        await context.bot.send_message(chat_id=target,text=receiver,parse_mode="HTML",disable_web_page_preview=True)
    except Exception as exc:
        fail_message_and_refund(mid,f"delivery_failed:{type(exc).__name__}")
        await msg.reply_text("📭 Não consegui entregar. Se havia cobrança anônima, ela foi devolvida.")
        return
    mark_message_delivered(mid)
    await _audit_relay(
        context,
        f"📨 <b>Mensagem V2 entregue</b>\nID: <code>#{mid}</code>\nDe: <code>{int(user.id)}</code>\nPara: <code>{target}</code>\nAnônima: {'sim' if anonymous else 'não'}\nTexto: {safe_text}",
    )
    await msg.reply_html(
        f"✅ <b>Mensagem enviada.</b>\nID: <code>#{mid}</code>" + (f"\nCusto: <b>{MSG_ANON_COST} coins</b>" if anonymous else "")
    )


async def msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message
    if not message: return
    parts=(message.text or "").split(maxsplit=2)
    if len(parts)<3:
        await message.reply_html("Uso: <code>/msg nickname mensagem</code>"); return
    await _deliver(update,context,parts[1],parts[2],False)


async def msganon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message
    if not message: return
    parts=(message.text or "").split(maxsplit=2)
    if len(parts)<3:
        await message.reply_html(f"Uso: <code>/msganon nickname mensagem</code>\nCusto: <b>{MSG_ANON_COST} coins</b>"); return
    await _deliver(update,context,parts[1],parts[2],True)


async def bloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message; user=update.effective_user
    if not message or not user or not await _gate(update,context): return
    if not context.args: await message.reply_html("Uso: <code>/bloquearmsg nickname</code>"); return
    target=find_identity_by_nickname(context.args[0])
    if not target: await message.reply_text("🔎 Nickname não encontrado."); return
    try: set_message_block(int(user.id),int(target["user_id"]),True)
    except MessageError as exc: await message.reply_html(_error_text(exc)); return
    await message.reply_text("🚫 Jogador bloqueado para mensagens.")


async def desbloquearmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message; user=update.effective_user
    if not message or not user or not await _gate(update,context): return
    if not context.args: await message.reply_html("Uso: <code>/desbloquearmsg nickname</code>"); return
    target=find_identity_by_nickname(context.args[0])
    if not target: await message.reply_text("🔎 Nickname não encontrado."); return
    set_message_block(int(user.id),int(target["user_id"]),False)
    await message.reply_text("✅ Jogador desbloqueado.")


async def msgconfig(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message; user=update.effective_user
    if not message or not user or not await _gate(update,context): return
    args=[x.lower() for x in context.args]
    if not args:
        s=get_message_settings(int(user.id))
        await message.reply_html(
            f"⚙️ <b>Mensagens</b>\nNormais: <b>{'on' if s['allow_messages'] else 'off'}</b>\nAnônimas: <b>{'on' if s['allow_anonymous'] else 'off'}</b>\n\n"
            "Use <code>/msgconfig on|off</code> ou <code>/msgconfig anon on|off</code>."
        ); return
    if len(args)==1 and args[0] in {'on','off'}:
        update_message_settings(int(user.id),allow_messages=args[0]=='on')
    elif len(args)==2 and args[0]=='anon' and args[1] in {'on','off'}:
        update_message_settings(int(user.id),allow_anonymous=args[1]=='on')
    else:
        await message.reply_text("⚠️ Configuração inválida."); return
    await message.reply_text("✅ Preferência de mensagens atualizada.")


async def denunciarmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message; user=update.effective_user
    if not message or not user or not await _gate(update,context): return
    if not context.args or not context.args[0].isdigit():
        await message.reply_html("Uso: <code>/denunciarmsg ID motivo</code>"); return
    reason=" ".join(context.args[1:]).strip()
    try: report_message(int(user.id),int(context.args[0]),reason)
    except MessageError as exc: await message.reply_html(_error_text(exc)); return
    await message.reply_text("🚨 Denúncia registrada para moderação.")


async def msgtutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message=update.effective_message
    if not message or not await _gate(update,context): return
    await message.reply_html(
        "💬 <b>Mensagens V2</b>\n\n"
        "<code>/msg nickname texto</code> — grátis\n"
        f"<code>/msganon nickname texto</code> — {MSG_ANON_COST} coins\n"
        "<code>/mensagens</code> — histórico e configurações\n"
        "<code>/bloquearmsg nickname</code> / <code>/desbloquearmsg nickname</code>\n"
        "<code>/denunciarmsg ID motivo</code>\n\n"
        "A identidade do remetente anônimo é preservada para moderação, mas não é mostrada ao destinatário."
    )


async def mensagens(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_webapp_entry(
        update,context,
        WebAppEntry(title="Central de Mensagens",description="Histórico recebido e enviado, privacidade, bloqueios e denúncias em um só lugar.",button="💬 Abrir Mensagens",path="/messages",icon="💬")
    )
