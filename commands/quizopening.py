from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data
from database import add_progress_xp

API = "https://api.animethemes.moe/anime"
AUDIO = "https://a.animethemes.moe/"
MUSIC_FALLBACK_API = "https://anime-music.jijidown.com/api/v2/music"
_THEME_CACHE: list[dict[str, str]] = []
QUIZ_XP = 5


def _catalog() -> list[dict[str, Any]]:
    data = build_cards_final_data()
    return [
        {**dict(meta), "anime_id": int(anime_id)}
        for anime_id, meta in (data.get("animes_by_id") or {}).items()
        if (meta or {}).get("anime")
    ]


def _parse_theme(payload: dict[str, Any]) -> dict[str, str] | None:
    anime = list(payload.get("anime") or [])
    if not anime:
        return None
    themes = list((anime[0] or {}).get("animethemes") or [])
    random.shuffle(themes)
    for theme in themes:
        entries = list((theme or {}).get("animethemeentries") or [])
        for entry in entries:
            if bool((entry or {}).get("nsfw")) or bool((entry or {}).get("spoiler")):
                continue
            videos = list((entry or {}).get("videos") or [])
            if not videos:
                continue
            filename = str((videos[0] or {}).get("filename") or "").strip()
            if not filename:
                continue
            return {
                "audio": AUDIO + filename + ".ogg",
                "type": str((theme or {}).get("type") or "OP"),
                "song": str(((theme or {}).get("song") or {}).get("title") or ""),
            }
    return None


async def _theme_for(anilist_id: int) -> dict[str, str] | None:
    params = {
        "filter[has]": "resources",
        "filter[site]": "AniList",
        "filter[external_id]": str(int(anilist_id)),
        "include": "animethemes.animethemeentries.videos,animethemes.song",
    }
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        response = await client.get(API, params=params)
        response.raise_for_status()
        return _parse_theme(response.json())


async def _fallback_random_theme() -> tuple[dict[str, Any], dict[str, str]] | None:
    """Independent provider used only when AnimeThemes is unavailable."""
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        response = await client.get(MUSIC_FALLBACK_API, params={"recommend": "true"})
        response.raise_for_status()
        body = response.json()
    item = dict(body.get("res") or {})
    anime_info = dict(item.get("anime_info") or {})
    anime_title = str(anime_info.get("title") or "").strip()
    play_url = str(item.get("play_url") or "").strip()
    if not anime_title or not play_url.startswith(("https://", "http://")):
        return None
    return (
        {"anime": anime_title, "anime_id": 0},
        {"audio": play_url, "type": str(item.get("type") or "OP"), "song": str(item.get("title") or "")},
    )


async def _media_works(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"Range": "bytes=0-2047"})
            return response.status_code in {200, 206} and len(response.content) > 128
    except Exception:
        return False


async def _pick_playable_theme(catalog: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]] | None:
    random.shuffle(_THEME_CACHE)
    for cached in list(_THEME_CACHE):
        if await _media_works(cached["audio"]):
            return ({"anime": cached["anime"], "anime_id": int(cached.get("anime_id") or 0)}, cached)
        _THEME_CACHE.remove(cached)

    candidates = random.sample(catalog, min(18, len(catalog)))
    for anime in candidates:
        anime_id = int(anime.get("anime_id") or 0)
        if anime_id <= 0:
            continue
        try:
            theme = await _theme_for(anime_id)
        except Exception:
            continue
        if theme and await _media_works(theme["audio"]):
            cached = {**theme, "anime": str(anime.get("anime") or ""), "anime_id": anime_id}
            _THEME_CACHE.append(cached)
            del _THEME_CACHE[:-50]
            return anime, theme

    try:
        fallback = await _fallback_random_theme()
    except Exception:
        fallback = None
    if fallback and await _media_works(fallback[1]["audio"]):
        return fallback
    return None


async def quizopening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, chat = update.effective_message, update.effective_chat
    if not message or not chat or chat.type not in ("group", "supergroup"):
        if message:
            await message.reply_text("Use /quizopening em um grupo.")
        return

    catalog = await asyncio.to_thread(_catalog)
    if len(catalog) < 4:
        await message.reply_text("O catálogo ainda não tem obras suficientes para este quiz.")
        return

    prepared = await _pick_playable_theme(catalog)
    if not prepared:
        await message.reply_text("Não encontrei uma faixa reproduzível agora. Tente novamente em alguns instantes.")
        return
    chosen, theme = prepared

    correct = str(chosen.get("anime") or "").strip()
    distractors = [str(x.get("anime") or "").strip() for x in catalog if str(x.get("anime") or "").strip() and str(x.get("anime") or "").strip() != correct]
    options = random.sample(list(dict.fromkeys(distractors)), 3) + [correct]
    random.shuffle(options)
    correct_index = options.index(correct)

    try:
        await context.bot.send_audio(
            chat_id=chat.id,
            audio=theme["audio"],
            caption="🎵 Ouça o trecho e marque de qual anime é esta abertura.",
            title="Quiz de Opening",
        )
    except Exception:
        await message.reply_text("A música selecionada não pôde ser entregue pelo Telegram. Tente outra rodada.")
        return

    poll_message = await context.bot.send_poll(
        chat_id=chat.id,
        question="De qual anime é esta música?",
        options=options,
        is_anonymous=False,
        allows_multiple_answers=False,
    )
    store = context.application.bot_data.setdefault("opening_quizzes", {})
    store[poll_message.poll.id] = {
        "chat_id": int(chat.id),
        "message_id": int(poll_message.message_id),
        "correct": int(correct_index),
        "anime": correct,
        "song": theme.get("song") or "",
        "closed": False,
    }


async def opening_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answer = update.poll_answer
    if not answer or not answer.user or not answer.option_ids:
        return
    store = context.application.bot_data.setdefault("opening_quizzes", {})
    locks = context.application.bot_data.setdefault("opening_quiz_locks", {})
    lock = locks.setdefault(answer.poll_id, asyncio.Lock())
    async with lock:
        game = store.get(answer.poll_id)
        if not game or game.get("closed"):
            return
        if int(answer.option_ids[0]) != int(game["correct"]):
            return
        game["closed"] = True
        try:
            await context.bot.stop_poll(chat_id=game["chat_id"], message_id=game["message_id"])
        except Exception:
            pass
        progress = await asyncio.to_thread(add_progress_xp, int(answer.user.id), QUIZ_XP)
    level = int((progress or {}).get("new_level") or 1)
    song = str(game.get("song") or "").strip()
    song_line = f"\n🎼 {song}" if song else ""
    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=f"🏆 {answer.user.mention_html()} acertou primeiro!\n\n🎬 <b>{game['anime']}</b>{song_line}\n⭐ +{QUIZ_XP} XP · nível {level}",
        parse_mode="HTML",
    )
