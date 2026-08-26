from __future__ import annotations

from typing import Any, Dict

from cards_service import build_cards_final_data
from collection_service import get_collection_state
from database import get_progress_row
from game_repository import get_wallet
from identity_repository import (
    IdentityError,
    NicknameTakenError,
    get_identity,
    public_display_name,
    sync_telegram_identity,
    update_profile_settings,
)
from level_system import get_rank


class ProfileServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def _favorite_payload(character_id: Any):
    try:
        character_id = int(character_id or 0)
    except (TypeError, ValueError):
        return None
    if character_id <= 0:
        return None

    character = (build_cards_final_data().get("characters_by_id") or {}).get(character_id)
    if not character:
        return None
    return {
        "id": character_id,
        "name": str(character.get("name") or "Personagem"),
        "anime": str(character.get("anime") or ""),
        "image": str(character.get("image") or ""),
    }


def get_profile_state(user_id: int) -> Dict[str, Any]:
    identity = get_identity(int(user_id))
    progress = get_progress_row(int(user_id)) or {}
    collection = get_collection_state(int(user_id))
    wallet = get_wallet(int(user_id))

    level = int(progress.get("level") or 1)
    xp = int(progress.get("xp") or 0)

    return {
        "user_id": int(user_id),
        "display_name": public_display_name(identity, int(user_id)),
        "telegram_username": str(identity.get("telegram_username") or ""),
        "telegram_full_name": str(identity.get("telegram_full_name") or ""),
        "nickname": str(identity.get("nickname") or ""),
        "private_profile": bool(identity.get("private_profile")),
        "country_code": str(identity.get("country_code") or ""),
        "favorite": _favorite_payload(identity.get("favorite_character_id")),
        "progress": {
            "xp": xp,
            "level": level,
            "rank": get_rank(level),
            "total_actions": int(progress.get("total_actions") or 0),
        },
        "collection": collection.get("stats") or {},
        "wallet": wallet,
    }


def sync_and_get_profile(user_id: int, username: str = "", full_name: str = "") -> Dict[str, Any]:
    sync_telegram_identity(int(user_id), username=username, full_name=full_name)
    return get_profile_state(int(user_id))


def update_profile(user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    favorite_supplied = "favorite_character_id" in payload
    favorite_id = payload.get("favorite_character_id") if favorite_supplied else None

    if favorite_supplied:
        try:
            favorite_number = int(favorite_id or 0)
        except (TypeError, ValueError) as exc:
            raise ProfileServiceError("invalid_favorite", "Personagem favorito inválido.") from exc
        if favorite_number:
            characters = build_cards_final_data().get("characters_by_id") or {}
            if favorite_number not in characters:
                raise ProfileServiceError("invalid_favorite", "Esse personagem não existe no catálogo atual.")
        favorite_id = favorite_number

    try:
        kwargs: Dict[str, Any] = {}
        if "nickname" in payload:
            kwargs["nickname"] = payload.get("nickname")
        if "private_profile" in payload:
            kwargs["private_profile"] = bool(payload.get("private_profile"))
        if favorite_supplied:
            kwargs["favorite_character_id"] = favorite_id
        if "country_code" in payload:
            kwargs["country_code"] = payload.get("country_code")

        update_profile_settings(int(user_id), **kwargs)
    except NicknameTakenError as exc:
        raise ProfileServiceError("nickname_taken", str(exc)) from exc
    except IdentityError as exc:
        raise ProfileServiceError("invalid_profile", str(exc)) from exc

    return get_profile_state(int(user_id))
