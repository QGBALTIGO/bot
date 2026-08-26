from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List

from identity_repository import get_identity
from ranking_repository import (
    get_coin_leaderboard,
    get_collection_leaderboard,
    get_general_leaderboard,
    get_level_leaderboard,
    get_user_positions,
)


def _flag(code: Any) -> str:
    value = str(code or "").strip().upper()
    if len(value) != 2 or not value.isalpha():
        return ""
    return "".join(chr(127397 + ord(ch)) for ch in value)


def _number(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize(rows: Iterable[Dict[str, Any]], viewer_id: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for position, row in enumerate(rows, start=1):
        payload = {
            key: _number(value)
            for key, value in row.items()
            if key != "user_id"
        }
        payload["position"] = position
        payload["display_name"] = str(payload.get("display_name") or "Jogador")[:64]
        payload["country_code"] = str(payload.get("country_code") or "")[:2]
        payload["flag"] = _flag(payload["country_code"])
        payload["is_viewer"] = int(row.get("user_id") or 0) == int(viewer_id)
        items.append(payload)
    return items


def get_ranking_state(viewer_id: int, *, limit: int = 20) -> Dict[str, Any]:
    viewer_id = int(viewer_id)
    identity = get_identity(viewer_id)
    is_private = bool(identity.get("private_profile"))

    positions = get_user_positions(viewer_id) if not is_private else {
        "level": 0,
        "collection": 0,
        "coins": 0,
    }

    return {
        "viewer": {
            "public": not is_private,
            "positions": positions,
        },
        "leaderboards": {
            "general": _serialize(get_general_leaderboard(limit), viewer_id),
            "level": _serialize(get_level_leaderboard(limit), viewer_id),
            "collection": _serialize(get_collection_leaderboard(limit), viewer_id),
            "coins": _serialize(get_coin_leaderboard(limit), viewer_id),
        },
        "rules": {
            "general": (
                "O ranking geral combina progresso (55%) e coleção (45%). "
                "Coins ficam fora do placar geral para evitar vantagem econômica ou pay-to-win."
            ),
            "privacy": (
                "Perfis privados não aparecem em rankings públicos. "
                "Ao tornar o perfil público novamente, a posição volta a ser calculada."
            ),
        },
    }
