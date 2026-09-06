from __future__ import annotations

from typing import Any, Mapping


ANIME_EMOJI = "🧧"
MOVIE_SERIES_EMOJI = "🍿"

_MOVIE_TYPES = {"film", "movie", "filme"}
_SERIES_TYPES = {"series", "serie", "tv", "tv_series", "tv-show", "tv_show"}


def normalize_card_media_type(value: Any) -> str:
    media_type = str(value or "").strip().lower().replace(" ", "_")
    if media_type in _MOVIE_TYPES:
        return "movie"
    if media_type in _SERIES_TYPES:
        return "series"
    return "anime"


def card_media_emoji(item: Mapping[str, Any] | None = None, *, anime_id: Any = 0) -> str:
    data = item or {}
    media_type = normalize_card_media_type(
        data.get("media_type") or data.get("work_type")
    )
    if media_type in {"movie", "series"}:
        return MOVIE_SERIES_EMOJI

    try:
        work_id = int(data.get("anime_id") or anime_id or 0)
    except (TypeError, ValueError):
        work_id = 0

    # Reserva do catálogo externo de cinema/séries. Mantém o emoji correto
    # durante a migração de registros antigos que ainda não tenham media_type.
    if 900_000_000 <= work_id < 1_000_000_000:
        return MOVIE_SERIES_EMOJI
    return ANIME_EMOJI
