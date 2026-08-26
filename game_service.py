from __future__ import annotations

import secrets
from typing import Any, Dict

from cards_service import build_cards_final_data
from game_repository import (
    ActiveDiceRollError,
    DiceRollExpiredError,
    InvalidDicePickError,
    NoDiceError,
    NoSpinsError,
    claim_daily,
    consume_spin,
    create_dice_roll,
    game_state,
    get_active_dice_roll,
    resolve_dice_roll,
)
from game_rules import SPIN_REWARDS, choose_spin_reward, spin_total_weight
from system_events import emit_completed_activity, emit_event


class GameServiceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def get_state(user_id: int) -> Dict[str, Any]:
    return game_state(int(user_id))


def claim_daily_reward(user_id: int) -> Dict[str, Any]:
    result = claim_daily(int(user_id))
    if result.get("claimed"):
        reward = result.get("reward") or {}
        streak = int(reward.get("streak") or 1)
        emit_event(
            int(user_id),
            "daily_claimed",
            label=f"🎁 Daily resgatado • sequência {streak}",
            metadata={"reward": reward},
        )
        emit_event(int(user_id), "daily_streak", amount=streak, absolute=True, label=f"🔥 Streak do Daily: {streak}")
        emit_completed_activity(int(user_id), label="Daily resgatado")
    return result


def _eligible_animes() -> list[Dict[str, Any]]:
    data = build_cards_final_data()
    characters_by_anime = data.get("characters_by_anime") or {}
    eligible: list[Dict[str, Any]] = []

    for anime in data.get("animes_list") or []:
        try:
            anime_id = int(anime.get("anime_id") or 0)
        except (TypeError, ValueError):
            continue
        if anime_id <= 0:
            continue
        if not characters_by_anime.get(anime_id):
            continue
        eligible.append(anime)

    return eligible


def roll_dice(user_id: int) -> Dict[str, Any]:
    active = get_active_dice_roll(int(user_id))
    if active:
        raise GameServiceError(
            "active_roll",
            "Você já tem uma rolagem ativa. Escolha uma obra antes de rolar novamente.",
        )

    eligible = _eligible_animes()
    if not eligible:
        raise GameServiceError(
            "cards_unavailable",
            "O catálogo de personagens ainda não está disponível.",
        )

    dice_value = secrets.randbelow(6) + 1
    dice_value = min(dice_value, len(eligible))
    selected = secrets.SystemRandom().sample(eligible, dice_value)

    options = [
        {
            "id": int(item["anime_id"]),
            "title": str(item.get("anime") or "Obra sem nome"),
            "cover": str(item.get("cover_image") or item.get("banner_image") or ""),
        }
        for item in selected
    ]

    try:
        result = create_dice_roll(int(user_id), dice_value, options)
    except NoDiceError as exc:
        raise GameServiceError(
            "no_dice",
            "Você está sem dados agora. O próximo dado chega automaticamente no horário indicado.",
        ) from exc
    except ActiveDiceRollError as exc:
        raise GameServiceError(
            "active_roll",
            "Você já tem uma rolagem ativa.",
        ) from exc

    emit_event(
        int(user_id),
        "dice_rolled",
        label=f"🎲 Dado rolado • {dice_value}",
        metadata={"dice_value": dice_value, "options": [item["id"] for item in options]},
    )
    return result


def pick_dice_anime(user_id: int, roll_token: str, anime_id: int) -> Dict[str, Any]:
    active = get_active_dice_roll(int(user_id))
    if not active:
        raise GameServiceError("roll_not_found", "Essa rolagem não está mais ativa.")

    if str(active.get("roll_token") or "") != str(roll_token or ""):
        raise GameServiceError("roll_mismatch", "A rolagem informada não pertence à sessão atual.")

    anime_id = int(anime_id)
    allowed = {int(item.get("id") or 0) for item in active.get("options") or []}
    if anime_id not in allowed:
        raise GameServiceError("anime_not_in_roll", "Essa obra não faz parte da rolagem atual.")

    data = build_cards_final_data()
    characters = list((data.get("characters_by_anime") or {}).get(anime_id) or [])
    if not characters:
        raise GameServiceError(
            "anime_without_characters",
            "Essa obra ficou sem personagens disponíveis. Role novamente.",
        )

    character = secrets.SystemRandom().choice(characters)
    character_id = int(character.get("id") or 0)
    if character_id <= 0:
        raise GameServiceError("invalid_character", "O personagem sorteado está inválido.")

    try:
        resolved = resolve_dice_roll(
            int(user_id),
            str(roll_token),
            anime_id,
            character_id,
        )
    except DiceRollExpiredError as exc:
        raise GameServiceError("roll_expired", "O tempo dessa rolagem acabou. Role o dado novamente.") from exc
    except InvalidDicePickError as exc:
        raise GameServiceError("invalid_pick", "Não foi possível confirmar essa escolha.") from exc

    character_payload = {
        "id": character_id,
        "name": str(character.get("name") or "Personagem"),
        "anime": str(character.get("anime") or ""),
        "image": str(character.get("image") or ""),
    }
    emit_event(
        int(user_id),
        "card_obtained",
        label=f"🎴 {character_payload['name']} entrou na coleção",
        metadata={"source": "dice", "character_id": character_id, "anime_id": anime_id},
    )
    emit_event(int(user_id), "dice_resolved", label=f"🎲 Dado concluído • {character_payload['anime']}")
    emit_completed_activity(int(user_id), label="Dado concluído")

    return {
        **resolved,
        "character": character_payload,
        "state": get_state(int(user_id)),
    }


def spin(user_id: int) -> Dict[str, Any]:
    total_weight = spin_total_weight()
    ticket = secrets.randbelow(total_weight)
    segment_index, reward = choose_spin_reward(ticket)

    try:
        result = consume_spin(int(user_id), segment_index, reward)
    except NoSpinsError as exc:
        raise GameServiceError(
            "no_spins",
            "Você está sem giros. Resgate o daily para conseguir novos giros.",
        ) from exc

    result["segments"] = [
        {
            "code": item.code,
            "label": item.label,
            "resource": item.resource,
            "amount": item.amount,
        }
        for item in SPIN_REWARDS
    ]
    emit_event(
        int(user_id),
        "spin_completed",
        label=f"🎡 Giro: {reward.label}",
        metadata={"reward_code": reward.code, "resource": reward.resource, "amount": reward.amount},
    )
    emit_completed_activity(int(user_id), label="Giro concluído")
    return result
