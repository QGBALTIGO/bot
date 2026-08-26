from __future__ import annotations

import random
from typing import Any, Dict, Optional

from cards_service import build_cards_final_data
from capture_repository import (
    CapturePurchaseError,
    claim_spawn,
    create_spawn_if_eligible,
    expire_spawn,
    get_active_spawn,
    get_recent_character_ids,
    purchase_captured_card,
    register_valid_activity,
)
from capture_rules import RECENT_CHARACTER_WINDOW, name_matches, valid_activity_text


class CaptureServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def _spawn_pool(chat_id: int) -> list[Dict[str, Any]]:
    data = build_cards_final_data()
    characters = [
        dict(item)
        for item in (data.get("characters_by_id") or {}).values()
        if isinstance(item, dict)
        and int(item.get("id") or 0) > 0
        and str(item.get("name") or "").strip()
        and str(item.get("image") or "").strip()
    ]
    if not characters:
        return []

    recent = set(get_recent_character_ids(int(chat_id), RECENT_CHARACTER_WINDOW))
    fresh = [item for item in characters if int(item.get("id") or 0) not in recent]
    return fresh or characters


def process_group_activity(chat_id: int, user_id: int, text: str) -> Optional[Dict[str, Any]]:
    if not valid_activity_text(text):
        return None
    activity = register_valid_activity(int(chat_id), int(user_id))
    if not activity.get("eligible"):
        return None

    pool = _spawn_pool(int(chat_id))
    if not pool:
        return None
    character = random.choice(pool)
    return create_spawn_if_eligible(int(chat_id), character)


def attempt_capture(chat_id: int, user_id: int, winner_name: str, guess: str) -> Dict[str, Any]:
    spawn = get_active_spawn(int(chat_id))
    if not spawn:
        raise CaptureServiceError("no_spawn", "Não há visitante ativo neste grupo agora.")

    expires_at = spawn.get("expires_at")
    if expires_at:
        from datetime import datetime

        if expires_at <= datetime.now(expires_at.tzinfo):
            expire_spawn(int(spawn["id"]))
            raise CaptureServiceError("expired", "Esse visitante acabou de escapar.")

    if not str(guess or "").strip():
        raise CaptureServiceError("missing_name", "Use /capturar Nome do Personagem.")
    if not name_matches(str(spawn.get("character_name") or ""), guess):
        raise CaptureServiceError("wrong_name", "Esse nome não corresponde ao visitante atual.")

    result = claim_spawn(
        int(spawn["id"]),
        int(user_id),
        str(winner_name or "Jogador"),
    )
    if not result.get("ok"):
        reason = str(result.get("reason") or "capture_failed")
        messages = {
            "expired": "Esse visitante acabou de escapar.",
            "not_active": "Outro jogador já encerrou essa captura.",
            "race_lost": "Outro jogador foi mais rápido nessa captura.",
            "not_found": "Esse visitante não está mais disponível.",
        }
        raise CaptureServiceError(reason, messages.get(reason, "Não foi possível concluir a captura."))
    return result


def buy_capture_offer(user_id: int, purchase_token: str) -> Dict[str, Any]:
    try:
        return purchase_captured_card(str(purchase_token or ""), int(user_id))
    except CapturePurchaseError as exc:
        code = str(exc)
        messages = {
            "offer_not_found": "Essa oferta não existe mais.",
            "not_owner": "Somente quem capturou pode comprar essa carta.",
            "already_purchased": "Essa carta já foi comprada.",
            "offer_unavailable": "Essa oferta não está mais disponível.",
            "offer_expired": "A janela de compra dessa carta expirou.",
            "insufficient_coins": "Você não tem coins suficientes para essa compra.",
            "purchase_race": "Essa compra já foi processada em outra solicitação.",
        }
        raise CaptureServiceError(code, messages.get(code, "Não foi possível concluir a compra.")) from exc
