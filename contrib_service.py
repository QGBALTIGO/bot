from __future__ import annotations

from urllib.parse import urlparse

from admin_repository import record_admin_event
from cards_service import (
    build_cards_final_data,
    override_add_anime,
    override_set_character_image,
)
from contrib_repository import (
    ContributionError,
    create_image_suggestion,
    create_work_suggestion,
    get_pending_contribution,
    list_pending_contributions,
    list_user_contributions,
    mark_contribution_reviewed,
)
from utils.runtime_guard import lock_manager


def _http_url(raw: str, *, required: bool = False) -> str:
    value = str(raw or "").strip()
    if not value:
        if required:
            raise ContributionError("Informe uma URL válida.")
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ContributionError("A URL precisa usar http ou https.")
    if len(value) > 2000:
        raise ContributionError("URL muito longa.")
    return value


def contribution_state(user_id: int) -> dict:
    data = build_cards_final_data()
    characters = [
        {"id": int(item["id"]), "name": str(item["name"]), "anime": str(item["anime"]), "image": str(item.get("image") or "")}
        for item in (data.get("characters_by_id") or {}).values()
    ]
    characters.sort(key=lambda item: (item["anime"].casefold(), item["name"].casefold()))
    return {
        "characters": characters,
        "mine": list_user_contributions(int(user_id)),
    }


def submit_image(user_id: int, payload: dict) -> dict:
    try:
        character_id = int(payload.get("character_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ContributionError("Personagem inválido.") from exc
    character = (build_cards_final_data().get("characters_by_id") or {}).get(character_id)
    if not character:
        raise ContributionError("Esse personagem não existe no catálogo atual.")
    url = _http_url(payload.get("image_url"), required=True)
    note = str(payload.get("note") or "").strip()[:700]
    return create_image_suggestion(
        int(user_id),
        character_id,
        str(character.get("name") or "Personagem"),
        str(character.get("image") or ""),
        url,
        note,
    )


def submit_work(user_id: int, payload: dict) -> dict:
    title = " ".join(str(payload.get("title") or "").split())
    if len(title) < 2 or len(title) > 220:
        raise ContributionError("Informe o nome da obra.")
    media_type = str(payload.get("media_type") or "anime").strip().lower()
    if media_type not in {"anime", "manga"}:
        raise ContributionError("Tipo de obra inválido.")
    raw_id = payload.get("anilist_id")
    anilist_id = None
    if raw_id not in (None, "", 0, "0"):
        try:
            anilist_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ContributionError("AniList ID inválido.") from exc
        if anilist_id <= 0:
            raise ContributionError("AniList ID inválido.")
    cover = _http_url(payload.get("cover_url"), required=False)
    note = str(payload.get("note") or "").strip()[:700]
    return create_work_suggestion(
        int(user_id), media_type, title, anilist_id=anilist_id, cover_url=cover, note=note
    )


def pending_for_admin() -> dict:
    return list_pending_contributions()


async def review_contribution(
    reviewer_id: int,
    *,
    kind: str,
    suggestion_id: int,
    decision: str,
    review_note: str = "",
) -> dict:
    kind = str(kind or "").strip().lower()
    decision = str(decision or "").strip().lower()
    if kind not in {"image", "work"}:
        raise ContributionError("Tipo de contribuição inválido.")
    if decision not in {"approved", "rejected"}:
        raise ContributionError("Decisão inválida.")

    suggestion = get_pending_contribution(kind, int(suggestion_id))
    if not suggestion:
        raise ContributionError("Sugestão não encontrada ou já revisada.")

    lock = await lock_manager.acquire(f"contrib:{kind}:{int(suggestion_id)}")
    try:
        suggestion = get_pending_contribution(kind, int(suggestion_id))
        if not suggestion:
            raise ContributionError("Sugestão não encontrada ou já revisada.")

        if decision == "approved":
            if kind == "image":
                override_set_character_image(
                    int(suggestion["character_id"]), str(suggestion["suggested_image_url"])
                )
            else:
                # Only anime shells are materialized automatically. Manga suggestions
                # remain an accepted editorial lead because the card catalog is anime-based.
                if str(suggestion.get("media_type") or "anime") == "anime":
                    anime_id = int(suggestion.get("anilist_id") or 0)
                    if anime_id > 0:
                        current = (build_cards_final_data().get("animes_by_id") or {}).get(anime_id)
                        if not current:
                            cover = str(suggestion.get("cover_url") or "")
                            override_add_anime(anime_id, str(suggestion.get("title") or "Nova obra"), cover, cover)

        reviewed = mark_contribution_reviewed(
            kind,
            int(suggestion_id),
            int(reviewer_id),
            decision,
            review_note,
        )
        record_admin_event(
            int(reviewer_id),
            "contribution_review",
            status=decision,
            target_type=kind,
            target_id=suggestion_id,
            metadata={
                "source_user_id": int(suggestion.get("user_id") or 0),
                "character_id": int(suggestion.get("character_id") or 0),
                "anilist_id": int(suggestion.get("anilist_id") or 0),
            },
        )
        return reviewed
    finally:
        lock.release()
