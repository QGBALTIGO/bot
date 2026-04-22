from __future__ import annotations

import duel_repository as repo
from duel_service import (
    build_group_keyboard,
    cancel_duel_if_missing_xcards,
    duel_constants,
    get_selectable_xcards,
    kickoff_private_setup,
    mode_label,
    player_display_name,
    player_state,
    refresh_duel_ui,
    render_group_text,
    schedule_duel_watch,
)
from telegram import Update
from telegram.ext import ContextTypes
from xcards_service import get_xcard_by_id


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and str(chat.type) in ("group", "supergroup"))


def _display_name(user) -> str:
    if not user:
        return "Jogador"
    return (user.full_name or user.first_name or user.username or f"User {user.id}").strip()


def _is_participant(duel: dict, user_id: int) -> bool:
    return int(user_id) in {
        int(duel.get("challenger_user_id") or 0),
        int(duel.get("challenged_user_id") or 0),
    }


def _selection_payload(card_ids: list[int]) -> list[dict]:
    payload: list[dict] = []
    for card_id in card_ids:
        card = get_xcard_by_id(int(card_id)) or {}
        if not card:
            continue
        payload.append(
            {
                "card_id": int(card.get("id") or 0),
                "card_no": str(card.get("card_no") or "").strip(),
                "name": str(card.get("name") or "").strip(),
                "title": str(card.get("title") or "").strip(),
                "image": str(card.get("image") or "").strip(),
                "rarity": str(card.get("rarity") or "").strip(),
                "bp_value": int(card.get("bp_value") or 0),
                "bp_display": str(card.get("bp") or card.get("bp_value") or "").strip(),
            }
        )
    return payload


async def duelo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return

    if not _is_group(update):
        await message.reply_html(
            "⚠️ <b>Use este comando no grupo</b>\n\n"
            "Responda a mensagem do jogador que você quer desafiar com <code>/duelo</code>."
        )
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_html(
            "⚠️ <b>Desafio inválido</b>\n\n"
            "Responda a mensagem do jogador que será desafiado e então envie <code>/duelo</code>."
        )
        return

    target = message.reply_to_message.from_user
    if int(target.id) == int(user.id):
        await message.reply_html("⚠️ Você não pode desafiar a si mesmo.")
        return

    if bool(getattr(target, "is_bot", False)):
        await message.reply_html("⚠️ Não é possível desafiar bots.")
        return

    config = duel_constants()
    result = repo.create_duel_challenge(
        challenger_user_id=int(user.id),
        challenger_username=getattr(user, "username", "") or "",
        challenger_full_name=_display_name(user),
        challenged_user_id=int(target.id),
        challenged_username=getattr(target, "username", "") or "",
        challenged_full_name=_display_name(target),
        group_chat_id=int(chat.id),
        group_chat_title=str(getattr(chat, "title", "") or getattr(chat, "full_name", "") or "").strip(),
        challenge_timeout_seconds=config["challenge_timeout_seconds"],
        prepare_timeout_seconds=config["selection_timeout_seconds"],
        round_timeout_seconds=config["round_timeout_seconds"],
    )

    if not result.get("ok"):
        error = str(result.get("error") or "")
        if error == "challenger_busy":
            await message.reply_html("⚠️ Você já está em outro duelo pendente ou ativo.")
            return
        if error == "challenged_busy":
            await message.reply_html("⚠️ Esse jogador já está em outro duelo pendente ou ativo.")
            return
        await message.reply_html("⚠️ Não consegui criar o duelo agora. Tente novamente em instantes.")
        return

    duel_id = int(result.get("duel_id") or 0)
    duel = repo.get_duel_bundle(duel_id)
    if not duel:
        await message.reply_html("⚠️ O duelo foi criado, mas não consegui carregar o estado dele.")
        return

    sent = await message.reply_html(
        render_group_text(duel),
        reply_markup=build_group_keyboard(duel),
        disable_web_page_preview=True,
    )
    duel = repo.set_duel_group_message(duel_id, int(sent.message_id)) or duel
    schedule_duel_watch(duel_id, context.application)
    await refresh_duel_ui(context.application, duel_id)


async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return

    data = str(query.data)

    if data.startswith("duelnp:"):
        await query.answer()
        return

    if data.startswith("duelacc:"):
        duel_id = int(data.split(":")[1])
        result = repo.respond_to_duel_challenge(
            duel_id=duel_id,
            actor_user_id=int(user.id),
            action="accept",
            private_timeout_seconds=duel_constants()["private_timeout_seconds"],
        )
        if not result.get("ok"):
            error = str(result.get("error") or "")
            if error == "not_target":
                await query.answer("Apenas o jogador desafiado pode aceitar.", show_alert=True)
                return
            if error == "expired":
                await refresh_duel_ui(context.application, duel_id)
                await query.answer("Esse desafio já expirou.", show_alert=True)
                return
            await query.answer("Não foi possível aceitar esse duelo.", show_alert=True)
            return

        await query.answer("Duelo aceito.")
        await kickoff_private_setup(context.application, duel_id)
        return

    if data.startswith("duelden:"):
        duel_id = int(data.split(":")[1])
        result = repo.respond_to_duel_challenge(
            duel_id=duel_id,
            actor_user_id=int(user.id),
            action="reject",
            private_timeout_seconds=duel_constants()["private_timeout_seconds"],
        )
        if not result.get("ok"):
            error = str(result.get("error") or "")
            if error == "not_target":
                await query.answer("Apenas o jogador desafiado pode negar.", show_alert=True)
                return
            await query.answer("Esse duelo não pode mais ser recusado.", show_alert=True)
            return

        await refresh_duel_ui(context.application, duel_id)
        await query.answer("Duelo recusado.")
        return

    if data.startswith("duelrdy:"):
        duel_id = int(data.split(":")[1])
        duel = repo.get_duel_bundle(duel_id)
        if not duel:
            await query.answer("Duelo não encontrado.", show_alert=True)
            return
        if not _is_participant(duel, int(user.id)):
            await query.answer("Só os participantes podem continuar esse duelo.", show_alert=True)
            return
        await query.answer("Tentando abrir o fluxo no privado...")
        await kickoff_private_setup(context.application, duel_id)
        return

    if data.startswith("duelmd:"):
        _, duel_id_raw, mode_raw = data.split(":")
        duel_id = int(duel_id_raw)
        mode = "wager" if mode_raw == "w" else "friendly"
        result = repo.propose_duel_mode(duel_id, int(user.id), mode)
        if not result.get("ok"):
            error = str(result.get("error") or "")
            if error == "only_challenger":
                await query.answer("Só quem iniciou o desafio escolhe o modo.", show_alert=True)
                return
            await query.answer("Esse modo não pode mais ser definido agora.", show_alert=True)
            return
        await refresh_duel_ui(context.application, duel_id)
        await query.answer(f"Modo definido: {mode_label(mode)}.")
        return

    if data.startswith("duelmok:"):
        duel_id = int(data.split(":")[1])
        result = repo.confirm_duel_mode(
            duel_id,
            int(user.id),
            selection_timeout_seconds=duel_constants()["selection_timeout_seconds"],
        )
        if not result.get("ok"):
            error = str(result.get("error") or "")
            if error == "only_challenged":
                await query.answer("Só o jogador desafiado pode confirmar o modo.", show_alert=True)
                return
            if error == "mode_missing":
                await query.answer("O modo ainda não foi escolhido.", show_alert=True)
                return
            if error == "insufficient_coins":
                await query.answer("Um dos jogadores não tem coin suficiente para o modo apostado.", show_alert=True)
                return
            await query.answer("Esse modo não pode mais ser confirmado.", show_alert=True)
            return
        duel_after = await cancel_duel_if_missing_xcards(context.application, duel_id)
        await refresh_duel_ui(context.application, duel_id)
        if duel_after and str(duel_after.get("state") or "") == "cancelled":
            await query.answer("Um dos jogadores não possui 3 XCARDs válidos para participar.", show_alert=True)
            return
        await query.answer("Modo confirmado. Hora de montar o trio.")
        return

    if data.startswith("duelnv:"):
        _, duel_id_raw, focus_raw = data.split(":")
        duel_id = int(duel_id_raw)
        duel = repo.get_duel_bundle(duel_id)
        if not duel:
            await query.answer("Duelo não encontrado.", show_alert=True)
            return
        if not _is_participant(duel, int(user.id)):
            await query.answer("Esse painel não é seu.", show_alert=True)
            return
        await refresh_duel_ui(context.application, duel_id, focus_overrides={int(user.id): int(focus_raw)})
        await query.answer()
        return

    if data.startswith("duelad:") or data.startswith("duelrm:"):
        prefix, duel_id_raw, focus_raw, card_id_raw = data.split(":")
        duel_id = int(duel_id_raw)
        focus_index = int(focus_raw)
        card_id = int(card_id_raw)
        duel = repo.get_duel_bundle(duel_id)
        if not duel:
            await query.answer("Duelo não encontrado.", show_alert=True)
            return
        if not _is_participant(duel, int(user.id)):
            await query.answer("Esse painel não é seu.", show_alert=True)
            return

        player = player_state(duel, int(user.id))
        selectable_ids = {int(item.get("card_id") or 0) for item in get_selectable_xcards(int(user.id), duel_id)}
        selected_ids = [int(value) for value in list(player.get("selected_card_ids") or [])]
        if prefix == "duelad":
            if card_id not in selectable_ids:
                await query.answer("Esse XCARD não está disponível para esse duelo.", show_alert=True)
                return
            if card_id not in selected_ids:
                if len(selected_ids) >= 3:
                    await query.answer("Seu trio já está cheio.", show_alert=True)
                    return
                selected_ids.append(card_id)
        else:
            selected_ids = [value for value in selected_ids if int(value) != int(card_id)]

        result = repo.save_team_draft(duel_id, int(user.id), selected_ids)
        if not result.get("ok"):
            await query.answer("Não consegui atualizar o seu trio agora.", show_alert=True)
            return
        await refresh_duel_ui(context.application, duel_id, focus_overrides={int(user.id): focus_index})
        await query.answer("Trio atualizado.")
        return

    if data.startswith("duelcf:"):
        duel_id = int(data.split(":")[1])
        duel = repo.get_duel_bundle(duel_id)
        if not duel:
            await query.answer("Duelo não encontrado.", show_alert=True)
            return
        if not _is_participant(duel, int(user.id)):
            await query.answer("Esse trio não é seu.", show_alert=True)
            return
        selected_ids = [int(value) for value in list(player_state(duel, int(user.id)).get("selected_card_ids") or [])]
        if len(selected_ids) != 3:
            await query.answer("Você precisa confirmar exatamente 3 XCARDs.", show_alert=True)
            return

        result = repo.confirm_duel_team(
            duel_id,
            int(user.id),
            cards_payload=_selection_payload(selected_ids),
            round_timeout_seconds=duel_constants()["round_timeout_seconds"],
        )
        if not result.get("ok"):
            error = str(result.get("error") or "")
            if error in {"sem_card", "card_bloqueado"}:
                await query.answer("Um dos seus XCARDs não está mais disponível para esse duelo.", show_alert=True)
                await refresh_duel_ui(context.application, duel_id)
                return
            if error == "entry_fee_insufficient":
                await refresh_duel_ui(context.application, duel_id)
                await query.answer("Alguém ficou sem coins para iniciar o modo apostado.", show_alert=True)
                return
            await query.answer("Não consegui travar seu trio agora.", show_alert=True)
            return

        schedule_duel_watch(duel_id, context.application)
        await refresh_duel_ui(context.application, duel_id)
        await query.answer("Trio confirmado.")
        return

    if data.startswith("duelrd:"):
        _, duel_id_raw, slot_raw = data.split(":")
        duel_id = int(duel_id_raw)
        slot = int(slot_raw)
        result = repo.submit_round_choice(
            duel_id,
            int(user.id),
            slot,
            round_timeout_seconds=duel_constants()["round_timeout_seconds"],
        )
        if not result.get("ok"):
            error = str(result.get("error") or "")
            if error in {"slot_eliminado", "slot_invalido", "slot_a_eliminado", "slot_b_eliminado"}:
                await query.answer("Esse personagem não pode ser usado nessa rodada.", show_alert=True)
                return
            await query.answer("Essa jogada não pode mais ser enviada.", show_alert=True)
            return

        schedule_duel_watch(duel_id, context.application)
        payload = result.get("payload") or {}
        await refresh_duel_ui(context.application, duel_id)
        if payload.get("round_resolved"):
            await query.answer("Rodada resolvida.")
        else:
            await query.answer("Jogada registrada.")
        return

    if data.startswith("duelsr:"):
        _, duel_id_raw, action = data.split(":")
        duel_id = int(duel_id_raw)
        if action == "ask":
            result = repo.set_surrender_pending(duel_id, int(user.id), True)
            if not result.get("ok"):
                await query.answer("Não foi possível abrir a desistência agora.", show_alert=True)
                return
            await refresh_duel_ui(context.application, duel_id)
            await query.answer("Confirme a desistência se realmente quiser sair.")
            return

        if action == "no":
            result = repo.set_surrender_pending(duel_id, int(user.id), False)
            if not result.get("ok"):
                await query.answer("Não foi possível fechar a desistência agora.", show_alert=True)
                return
            await refresh_duel_ui(context.application, duel_id)
            await query.answer("Desistência cancelada.")
            return

        if action == "ok":
            result = repo.confirm_surrender(duel_id, int(user.id))
            if not result.get("ok"):
                await query.answer("Não foi possível confirmar sua desistência.", show_alert=True)
                return
            await refresh_duel_ui(context.application, duel_id)
            await query.answer("Duelo encerrado por desistência.")
            return

    await query.answer()
