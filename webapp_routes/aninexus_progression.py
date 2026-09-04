from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from database_aninexus_progression_source import (
    MAX_PASS_LEVEL,
    PASS_MILESTONES,
    SEASON_ID,
    SEASON_NAME,
    claim_pass_reward,
    claim_quest,
    claimed_pass_levels,
    get_source_profile,
    is_quest_claimed,
    metric_value,
    pass_tracks,
    source_level_progress,
)
from webapp_routes.aninexus_compat import API_PREFIX, _require_user, _unauthorized


QUESTS: dict[str, dict[str, Any]] = {
    "daily_game_1": {
        "period": "daily",
        "name": "Primeira partida",
        "description": "Conclua 1 partida nos Jogos AniNexus.",
        "metric": "games_completed",
        "target": 1,
        "reward_coins": 1,
        "reward_xp": 3,
    },
    "daily_dado_1": {
        "period": "daily",
        "name": "Tente a sorte",
        "description": "Use o Dado AniNexus 1 vez.",
        "metric": "dado_rolls",
        "target": 1,
        "reward_coins": 1,
        "reward_xp": 3,
    },
    "daily_game_2": {
        "period": "daily",
        "name": "Treino completo",
        "description": "Conclua 2 partidas nos Jogos AniNexus.",
        "metric": "games_completed",
        "target": 2,
        "reward_coins": 0,
        "reward_xp": 5,
    },
    "weekly_games_5": {
        "period": "weekly",
        "name": "Jogador da semana",
        "description": "Conclua 5 partidas nos Jogos AniNexus nesta semana.",
        "metric": "games_completed",
        "target": 5,
        "reward_coins": 2,
        "reward_xp": 10,
    },
    "weekly_dado_5": {
        "period": "weekly",
        "name": "Cinco rolagens",
        "description": "Use o Dado AniNexus 5 vezes nesta semana.",
        "metric": "dado_rolls",
        "target": 5,
        "reward_coins": 2,
        "reward_xp": 10,
    },
    "weekly_games_10": {
        "period": "weekly",
        "name": "Especialista em jogos",
        "description": "Conclua 10 partidas nos Jogos AniNexus nesta semana.",
        "metric": "games_completed",
        "target": 10,
        "reward_coins": 2,
        "reward_xp": 15,
    },
}

ACHIEVEMENTS = [
    ("first_character", "Primeiro personagem", "Adicione seu primeiro personagem à coleção.", "unique_collection", 1),
    ("collector_10", "Colecionador I", "Tenha 10 personagens diferentes.", "unique_collection", 10),
    ("collector_50", "Colecionador II", "Tenha 50 personagens diferentes.", "unique_collection", 50),
    ("collector_100", "Colecionador III", "Tenha 100 personagens diferentes.", "unique_collection", 100),
    ("level_10", "Explorador", "Alcance o nível 10.", "level", 10),
    ("level_25", "Veterano", "Alcance o nível 25.", "level", 25),
    ("level_50", "Mestre", "Alcance o nível 50.", "level", 50),
]


def _error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def _quest_item(user_id: int, quest_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    progress = metric_value(
        user_id,
        str(definition["metric"]),
        str(definition["period"]),
    )
    target = int(definition["target"])
    return {
        "id": quest_id,
        "name": str(definition["name"]),
        "description": str(definition["description"]),
        "icon": "◉",
        "reward_xp": int(definition["reward_xp"]),
        "reward_shards": int(definition["reward_coins"]),
        "progress": min(target, max(0, progress)),
        "target": target,
        "claimed": is_quest_claimed(user_id, quest_id, str(definition["period"])),
        "locked": False,
    }


def build_aninexus_progression_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-progression"])

    def achievements(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        out = []
        for achievement_id, name, description, metric, target in ACHIEVEMENTS:
            value = metric_value(user_id, metric, "weekly")
            out.append(
                {
                    "id": achievement_id,
                    "name": name,
                    "description": description,
                    "icon": "🏆",
                    "reward_xp": 0,
                    "unlocked": value >= int(target),
                }
            )
        return JSONResponse(out)

    def quests(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        daily = [
            _quest_item(user_id, quest_id, definition)
            for quest_id, definition in QUESTS.items()
            if definition["period"] == "daily"
        ]
        weekly = [
            _quest_item(user_id, quest_id, definition)
            for quest_id, definition in QUESTS.items()
            if definition["period"] == "weekly"
        ]
        return JSONResponse({"daily": daily, "weekly": weekly, "pass": [], "pass_type": "free"})

    def claim_quest_endpoint(quest_id: str, authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        definition = QUESTS.get(str(quest_id))
        if not definition:
            return _error("quest_not_found", "Missão não encontrada.", 404)

        result = claim_quest(
            int(session_user.get("id") or 0),
            str(quest_id),
            str(definition["period"]),
            metric=str(definition["metric"]),
            target=int(definition["target"]),
            reward_coins=int(definition["reward_coins"]),
            reward_xp=int(definition["reward_xp"]),
        )
        if result.get("ok"):
            return JSONResponse(
                {
                    "success": True,
                    "reward_xp": int(result.get("reward_xp") or 0),
                    "reward_shards": int(result.get("reward_coins") or 0),
                }
            )
        code = str(result.get("error") or "quest_error")
        messages = {
            "quest_incomplete": "Você ainda não concluiu esta missão.",
            "already_claimed": "Esta recompensa já foi resgatada.",
        }
        return _error(code, messages.get(code, "Não foi possível resgatar esta missão."))

    def pass_data(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        progress = source_level_progress(user_id)
        return JSONResponse(
            {
                **progress,
                "season_id": SEASON_ID,
                "season_name": SEASON_NAME,
                "pass_type": "free",
                "pass_bank": {},
                "pass_bank_total": 0,
                "claimed_levels": claimed_pass_levels(user_id),
                "tracks": pass_tracks(),
                "milestones": PASS_MILESTONES,
                "max_level": MAX_PASS_LEVEL,
                "prices": {"free": 0},
                "currency": "COINS",
                "upgrade_prices": {},
                "level_buy_cost": 0,
                "benefits": {
                    "free": {
                        "hunt_multiplier": 1.0,
                        "egg_drop_multiplier": 1.0,
                        "incubation_multiplier": 1.0,
                        "incubation_slots": 1,
                    }
                },
                "tiers": {"free": {"name": "Grátis", "summary": "Trilha padrão da temporada AniNexus."}},
            }
        )

    def claim_level(level: int, authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = claim_pass_reward(int(session_user.get("id") or 0), int(level))
        if result.get("ok"):
            return JSONResponse(
                {
                    "status": str(result.get("status") or "success"),
                    "shards": int(result.get("coins") or 0),
                    "eggs": int(result.get("dados") or 0),
                    "xp": int(result.get("xp") or 0),
                }
            )
        code = str(result.get("error") or "pass_claim_error")
        messages = {
            "invalid_level": "Este nível não possui recompensa.",
            "level_not_reached": f"Você ainda não alcançou o nível {level}.",
        }
        return _error(code, messages.get(code, "Não foi possível resgatar esta recompensa."))

    def buy_level(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        return _error("level_purchase_disabled", "Os níveis da temporada são conquistados pelo XP real do Source.")

    def claim_bank(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        return _error("no_pass_bank", "A temporada AniNexus não usa cofre separado.")

    router.add_api_route("/achievements/list", achievements, methods=["GET"])
    router.add_api_route("/quests", quests, methods=["GET"])
    router.add_api_route("/quests/claim/{quest_id}", claim_quest_endpoint, methods=["POST"])
    router.add_api_route("/pass_data", pass_data, methods=["GET"])
    router.add_api_route("/claim_level/{level}", claim_level, methods=["POST"])
    router.add_api_route("/buy_level", buy_level, methods=["POST"])
    router.add_api_route("/claim_bank", claim_bank, methods=["POST"])
    return router
