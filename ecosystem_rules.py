from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

MEDIA_TYPES = {"anime", "manga"}
LIBRARY_STATUSES = {"favorite", "planned", "watching", "completed", "paused", "dropped"}
NOTIFICATION_KINDS = {
    "daily",
    "dice_full",
    "messages",
    "duels",
    "trades",
    "requests",
    "news",
    "airing",
    "missions",
    "achievements",
}


@dataclass(frozen=True)
class MissionDefinition:
    code: str
    label: str
    description: str
    event_code: str
    target: int
    period: str
    xp_reward: int = 0
    coin_reward: int = 0


@dataclass(frozen=True)
class AchievementDefinition:
    code: str
    label: str
    description: str
    event_code: str
    target: int
    title: str = ""


MISSIONS: tuple[MissionDefinition, ...] = (
    MissionDefinition("daily_play", "Entre em ação", "Conclua 2 atividades válidas hoje.", "activity_completed", 2, "daily", xp_reward=5),
    MissionDefinition("daily_game", "Hora de jogar", "Conclua 1 minigame hoje.", "minigame_completed", 1, "daily", coin_reward=2),
    MissionDefinition("daily_collect", "Colecionador do dia", "Ganhe 1 card hoje.", "card_obtained", 1, "daily", xp_reward=4),
    MissionDefinition("weekly_social", "Vida social", "Faça 3 interações sociais na semana.", "social_interaction", 3, "weekly", xp_reward=10, coin_reward=4),
    MissionDefinition("weekly_games", "Maratona", "Conclua 7 jogos na semana.", "minigame_completed", 7, "weekly", xp_reward=15, coin_reward=6),
    MissionDefinition("weekly_collection", "Álbum em crescimento", "Ganhe 10 cards na semana.", "card_obtained", 10, "weekly", xp_reward=15, coin_reward=5),
)

ACHIEVEMENTS: tuple[AchievementDefinition, ...] = (
    AchievementDefinition("first_card", "Primeiro card", "Conquiste seu primeiro personagem.", "card_obtained", 1, "Colecionador Iniciante"),
    AchievementDefinition("cards_25", "Primeiras páginas", "Conquiste 25 cards.", "card_obtained", 25, "Caçador de Cards"),
    AchievementDefinition("cards_100", "Coleção centenária", "Conquiste 100 cards.", "card_obtained", 100, "Arquivista Baltigo"),
    AchievementDefinition("first_capture", "Peguei!", "Acerte sua primeira captura em grupo.", "capture_won", 1, "Caçador"),
    AchievementDefinition("captures_25", "Caçador experiente", "Vença 25 capturas.", "capture_won", 25, "Rastreador de Lendas"),
    AchievementDefinition("first_duel", "Primeiro duelo", "Conclua um duelo.", "duel_completed", 1, "Duelista"),
    AchievementDefinition("duel_wins_10", "Sequência de vitórias", "Vença 10 duelos.", "duel_won", 10, "Duelista de Elite"),
    AchievementDefinition("termo_10", "Palavra na ponta da língua", "Vença 10 Termos diários.", "termo_won", 10, "Mestre do Termo"),
    AchievementDefinition("memory_10", "Memória afiada", "Conclua 10 partidas de Memória.", "memory_completed", 10, "Mente de Aço"),
    AchievementDefinition("streak_7", "Uma semana a bordo", "Alcance 7 dias de Daily.", "daily_streak", 7, "Tripulante Fiel"),
    AchievementDefinition("social_25", "Conhecido no convés", "Faça 25 interações sociais.", "social_interaction", 25, "Companheiro de Bordo"),
)

MISSION_BY_CODE = {item.code: item for item in MISSIONS}
ACHIEVEMENT_BY_CODE = {item.code: item for item in ACHIEVEMENTS}


def normalize_media_type(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value not in MEDIA_TYPES:
        raise ValueError("media_type_invalid")
    return value


def normalize_library_status(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value not in LIBRARY_STATUSES:
        raise ValueError("library_status_invalid")
    return value


def mission_period_key(period: str, current: date) -> str:
    if period == "daily":
        return current.isoformat()
    if period == "weekly":
        year, week, _ = current.isocalendar()
        return f"{year}-W{week:02d}"
    raise ValueError("mission_period_invalid")


def event_category(event_code: str) -> str:
    code = str(event_code or "")
    if code.startswith(("message_", "friend_", "trade_", "duel_")) or code == "social_interaction":
        return "social"
    if code.startswith(("card_", "capture_", "xcard_")):
        return "collection"
    if code.startswith(("termo_", "memory_", "dice_", "spin_", "daily_")) or code == "minigame_completed":
        return "game"
    if code.startswith(("watchlist_", "favorite_", "news_", "airing_")):
        return "explore"
    return "system"
