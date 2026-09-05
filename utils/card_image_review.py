from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from psycopg.rows import dict_row
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from cards_service import build_cards_final_data, find_anime, override_set_character_image
from database import get_all_global_character_images, pool
from utils.aninexus_admin import is_admin
from utils.card_image_review_rules import score_zerochan_post, zerochan_queries
from utils.portrait_image import crop_portrait_bytes
from utils.public_character_image import public_origin

logger = logging.getLogger(__name__)

REVIEW_CHANNEL = (
    os.getenv("CARD_IMAGE_REVIEW_CHANNEL", "").strip()
    or os.getenv("CANAL_PEDIDOS", "").strip()
)
PUBLIC_BASE_URL = public_origin().rstrip("/")
ZEROCHAN_USER = os.getenv("ZEROCHAN_USER", "kaykys468").strip() or "kaykys468"
ZEROCHAN_AGENT = f"SourceBaltigo-Curation - {ZEROCHAN_USER}"
OPTIONS_PER_CHARACTER = max(3, min(10, int(os.getenv("CARD_IMAGE_REVIEW_OPTIONS", "10"))))
MAX_ROUNDS = max(1, min(5, int(os.getenv("CARD_IMAGE_REVIEW_MAX_ROUNDS", "3"))))
AUTO_ANIME_IDS = tuple(
    int(part.strip())
    for part in os.getenv("CARD_IMAGE_REVIEW_AUTO_ANIME_IDS", "").split(",")
    if part.strip().isdigit()
)
_ZEROCHAN_RATE_LOCK = threading.Lock()
_ZEROCHAN_NEXT_REQUEST_AT = 0.0

@dataclass(frozen=True)
class Candidate:
    post_id: int
    source_page: str
    source_url: str
    image_url: str
    width: int
    height: int
    score: float
    artist: str


def ensure_review_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS card_image_review_queue (
                    character_id BIGINT PRIMARY KEY,
                    anime_id BIGINT NOT NULL,
                    character_name TEXT NOT NULL,
                    anime_title TEXT NOT NULL,
                    current_image_url TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'queued',
                    round_no INTEGER NOT NULL DEFAULT 0,
                    approved_candidate_id BIGINT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS card_image_review_candidates (
                    id BIGSERIAL PRIMARY KEY,
                    character_id BIGINT NOT NULL,
                    anime_id BIGINT NOT NULL,
                    option_no INTEGER NOT NULL,
                    round_no INTEGER NOT NULL,
                    zerochan_post_id BIGINT NOT NULL,
                    source_page TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    artist TEXT NOT NULL DEFAULT '',
                    score DOUBLE PRECISION NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by BIGINT,
                    reviewed_at TIMESTAMPTZ,
                    channel_message_id BIGINT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(character_id, zerochan_post_id)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_image_review_queue_status ON card_image_review_queue(status, position)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_image_review_candidates_character ON card_image_review_candidates(character_id, status)"
            )
        conn.commit()


def _throttle_zerochan() -> None:
    global _ZEROCHAN_NEXT_REQUEST_AT
    with _ZEROCHAN_RATE_LOCK:
        now = time.monotonic()
        delay = max(0.0, _ZEROCHAN_NEXT_REQUEST_AT - now)
        if delay:
            time.sleep(delay)
        _ZEROCHAN_NEXT_REQUEST_AT = time.monotonic() + 1.15


def _fetch_json(url: str) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        _throttle_zerochan()
        request = Request(url, headers={"User-Agent": ZEROCHAN_AGENT, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError("zerochan_request_failed") from last_error


def _telegram_photo(source_url: str, post_id: int) -> io.BytesIO:
    request = Request(
        str(source_url),
        headers={
            "User-Agent": ZEROCHAN_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.zerochan.net/",
        },
    )
    with urlopen(request, timeout=45) as response:
        content = response.read(12 * 1024 * 1024 + 1)
    if not content or len(content) > 12 * 1024 * 1024:
        raise ValueError("invalid_review_image_size")
    portrait, _metadata = crop_portrait_bytes(content)
    stream = io.BytesIO(portrait)
    stream.name = f"character-{int(post_id)}.jpg"
    return stream


def fetch_zerochan_candidates(name: str, excluded_post_ids: set[int], limit: int) -> list[Candidate]:
    ranked: dict[int, tuple[float, dict[str, Any]]] = {}
    successful_searches = 0
    failed_searches = 0
    for query in zerochan_queries(name):
        url = f"https://www.zerochan.net/{quote(query, safe='+')}?json&strict&s=fav&t=0&l=100"
        try:
            payload = _fetch_json(url)
            successful_searches += 1
        except Exception as exc:
            failed_searches += 1
            logger.warning("Zerochan search failed query=%s error=%s", query, type(exc).__name__)
            continue
        rows = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
        for post in rows:
            post_id = int(post.get("id") or 0)
            if post_id <= 0 or post_id in excluded_post_ids:
                continue
            score = score_zerochan_post(post)
            if score is not None and (post_id not in ranked or score > ranked[post_id][0]):
                ranked[post_id] = (score, post)
        if len(ranked) >= limit * 3:
            break

    if successful_searches == 0:
        raise RuntimeError("zerochan_unavailable")
    if not ranked and failed_searches:
        raise RuntimeError("zerochan_partial_failure")

    results: list[Candidate] = []
    for post_id, (score, post) in sorted(ranked.items(), key=lambda item: item[1][0], reverse=True):
        if len(results) >= limit:
            break
        try:
            detail = _fetch_json(f"https://www.zerochan.net/{post_id}?json")
            source_url = str(detail.get("full") or "").strip()
            if not source_url.startswith("https://"):
                continue
            tags = [str(tag) for tag in (detail.get("tags") or post.get("tags") or [])]
            artist = next((tag for tag in tags if tag.lower() == "behindxa"), "")
            if not artist:
                artist = next((tag for tag in tags if tag.lower().startswith("pixiv id ")), "")
            image_url = source_url
            if PUBLIC_BASE_URL:
                image_url = f"{PUBLIC_BASE_URL}/api/image-proxy?{urlencode({'crop': 'portrait', 'url': source_url})}"
            results.append(Candidate(
                post_id=post_id,
                source_page=f"https://www.zerochan.net/{post_id}",
                source_url=source_url,
                image_url=image_url,
                width=int(detail.get("width") or post.get("width") or 0),
                height=int(detail.get("height") or post.get("height") or 0),
                score=score,
                artist=artist,
            ))
        except Exception as exc:
            logger.warning("Zerochan detail failed id=%s error=%s", post_id, type(exc).__name__)
    return results


def seed_anime_review(anime_id: int) -> dict[str, int]:
    ensure_review_tables()
    data = build_cards_final_data(force_reload=True)
    anime = (data.get("animes_by_id") or {}).get(int(anime_id))
    if not anime:
        raise ValueError("anime_not_found")
    characters = list((data.get("characters_by_anime") or {}).get(int(anime_id), []))
    protected_ids = set(get_all_global_character_images())
    inserted = skipped = 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for position, character in enumerate(characters, start=1):
                cid = int(character["id"])
                if cid in protected_ids:
                    skipped += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO card_image_review_queue
                        (character_id, anime_id, character_name, anime_title, current_image_url, position)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (character_id) DO NOTHING
                    """,
                    (cid, int(anime_id), str(character["name"]), str(anime["anime"]), str(character.get("image") or ""), position),
                )
                inserted += max(0, int(cur.rowcount or 0))
        conn.commit()
    return {"inserted": inserted, "protected": skipped, "total": len(characters)}


def _next_queue_row() -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT q.* FROM card_image_review_queue q
                WHERE q.status = 'queued' AND q.round_no < %s
                  AND NOT EXISTS (
                      SELECT 1 FROM card_image_review_queue active
                      WHERE active.status = 'reviewing'
                  )
                ORDER BY anime_id, position
                LIMIT 1
                """,
                (MAX_ROUNDS,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _existing_posts(character_id: int) -> set[int]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT zerochan_post_id FROM card_image_review_candidates WHERE character_id=%s", (int(character_id),))
            return {int(row[0] if not isinstance(row, dict) else row["zerochan_post_id"]) for row in cur.fetchall()}


def _store_candidates(row: dict[str, Any], candidates: list[Candidate]) -> list[dict[str, Any]]:
    round_no = int(row.get("round_no") or 0) + 1
    stored: list[dict[str, Any]] = []
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE card_image_review_queue SET status='reviewing', round_no=%s, updated_at=NOW() WHERE character_id=%s AND status='queued'",
                (round_no, int(row["character_id"])),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return []
            for option_no, candidate in enumerate(candidates, start=1):
                cur.execute(
                    """
                    INSERT INTO card_image_review_candidates
                        (character_id, anime_id, option_no, round_no, zerochan_post_id, source_page,
                         source_url, image_url, width, height, artist, score)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (character_id, zerochan_post_id) DO NOTHING
                    RETURNING *
                    """,
                    (int(row["character_id"]), int(row["anime_id"]), option_no, round_no,
                     candidate.post_id, candidate.source_page, candidate.source_url, candidate.image_url,
                     candidate.width, candidate.height, candidate.artist, candidate.score),
                )
                result = cur.fetchone()
                if result:
                    stored.append(dict(result))
        conn.commit()
    return stored


def _mark_no_candidates(character_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE card_image_review_queue SET status='exhausted', updated_at=NOW() WHERE character_id=%s",
                (int(character_id),),
            )
        conn.commit()


def _mark_protected(character_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE card_image_review_queue
                SET status='protected', updated_at=NOW()
                WHERE character_id=%s AND status='queued'
                """,
                (int(character_id),),
            )
        conn.commit()


def _recover_failed_deliveries(anime_id: int) -> int:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE card_image_review_queue q
                SET status='queued', round_no=0, updated_at=NOW()
                WHERE q.anime_id=%s
                  AND q.status NOT IN ('approved', 'protected')
                  AND EXISTS (
                      SELECT 1 FROM card_image_review_candidates c
                      WHERE c.character_id=q.character_id
                        AND c.status='send_failed'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM card_image_review_candidates c
                      WHERE c.character_id=q.character_id
                        AND c.status='pending'
                  )
                """,
                (int(anime_id),),
            )
            recovered = int(cur.rowcount or 0)
            cur.execute(
                """
                DELETE FROM card_image_review_candidates c
                USING card_image_review_queue q
                WHERE c.character_id=q.character_id
                  AND q.anime_id=%s
                  AND q.status='queued'
                  AND c.status='send_failed'
                """,
                (int(anime_id),),
            )
        conn.commit()
    return recovered


def _caption(queue_row: dict[str, Any], candidate: dict[str, Any], total_options: int) -> str:
    artist = str(candidate.get("artist") or "").strip()
    artist_line = f"\n🎨 {html.escape(artist)}" if artist else ""
    return (
        f"🖼 <b>REVISÃO DE FOTO</b>\n\n"
        f"👤 <b>{html.escape(str(queue_row['character_name']))}</b> — ID <code>{int(queue_row['character_id'])}</code>\n"
        f"📺 {html.escape(str(queue_row['anime_title']))}\n"
        f"🔢 Opção {int(candidate['option_no'])}/{int(total_options)} · lote {int(candidate['round_no'])}"
        f"{artist_line}\n"
        f"🔗 <a href=\"{html.escape(str(candidate['source_page']), quote=True)}\">Ver fonte</a>\n\n"
        "A imagem só será aplicada depois da aprovação."
    )


def _keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Usar esta", callback_data=f"imgrev:a:{candidate_id}"), InlineKeyboardButton("❌ Rejeitar", callback_data=f"imgrev:r:{candidate_id}")]])


async def _dispatch_next_character(application) -> bool:
    if not REVIEW_CHANNEL:
        return False
    row = await asyncio.to_thread(_next_queue_row)
    if not row:
        return False
    current_overrides = await asyncio.to_thread(get_all_global_character_images)
    if int(row["character_id"]) in current_overrides:
        await asyncio.to_thread(_mark_protected, int(row["character_id"]))
        return False
    excluded = await asyncio.to_thread(_existing_posts, int(row["character_id"]))
    candidates = await asyncio.to_thread(fetch_zerochan_candidates, str(row["character_name"]), excluded, OPTIONS_PER_CHARACTER)
    if not candidates:
        await asyncio.to_thread(_mark_no_candidates, int(row["character_id"]))
        return False
    stored = await asyncio.to_thread(_store_candidates, row, candidates)
    sent = 0
    for candidate in stored:
        try:
            photo = await asyncio.to_thread(
                _telegram_photo,
                str(candidate["source_url"]),
                int(candidate["zerochan_post_id"]),
            )
            message = await application.bot.send_photo(
                chat_id=REVIEW_CHANNEL,
                photo=photo,
                caption=_caption(row, candidate, len(stored)),
                parse_mode="HTML",
                reply_markup=_keyboard(int(candidate["id"])),
            )
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE card_image_review_candidates SET channel_message_id=%s WHERE id=%s", (int(message.message_id), int(candidate["id"])))
                conn.commit()
            sent += 1
        except Exception:
            logger.exception("Failed to publish image review candidate id=%s", candidate["id"])
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE card_image_review_candidates SET status='send_failed' WHERE id=%s AND status='pending'",
                        (int(candidate["id"]),),
                    )
                conn.commit()
        await asyncio.sleep(0.35)
    if sent == 0:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE card_image_review_queue SET status='queued', updated_at=NOW() WHERE character_id=%s AND status='reviewing'",
                    (int(row["character_id"]),),
                )
            conn.commit()
    return sent > 0


async def dispatch_next_character(application) -> bool:
    lock = application.bot_data.get("card_image_review_dispatch_lock")
    if lock is None:
        lock = asyncio.Lock()
        application.bot_data["card_image_review_dispatch_lock"] = lock
    async with lock:
        return await _dispatch_next_character(application)


def _candidate(candidate_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT c.*, q.character_name, q.anime_title, q.status AS queue_status
                   FROM card_image_review_candidates c
                   JOIN card_image_review_queue q ON q.character_id=c.character_id
                   WHERE c.id=%s LIMIT 1""",
                (int(candidate_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _approve(candidate_id: int, admin_id: int) -> dict[str, Any] | None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT c.*, q.character_name, q.anime_title,
                       q.status AS queue_status
                FROM card_image_review_candidates c
                JOIN card_image_review_queue q ON q.character_id=c.character_id
                WHERE c.id=%s
                FOR UPDATE OF c, q
                """,
                (int(candidate_id),),
            )
            row = cur.fetchone()
            if not row or row["status"] != "pending" or row["queue_status"] != "reviewing":
                conn.rollback()
                return None
            cur.execute(
                "UPDATE card_image_review_candidates SET status='approved', reviewed_by=%s, reviewed_at=NOW() WHERE id=%s",
                (int(admin_id), int(candidate_id)),
            )
            cur.execute(
                "UPDATE card_image_review_candidates SET status='superseded', reviewed_by=%s, reviewed_at=NOW() WHERE character_id=%s AND id<>%s AND status='pending'",
                (int(admin_id), int(row["character_id"]), int(candidate_id)),
            )
            cur.execute(
                "UPDATE card_image_review_queue SET status='approved', approved_candidate_id=%s, updated_at=NOW() WHERE character_id=%s",
                (int(candidate_id), int(row["character_id"])),
            )
            override_set_character_image(
                int(row["character_id"]),
                str(row["image_url"]),
                updated_by=int(admin_id),
            )
        conn.commit()
    return dict(row)


def _review_counts() -> dict[str, int]:
    ensure_review_tables()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) FROM card_image_review_queue GROUP BY status"
            )
            return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def _candidate_message_ids(character_id: int, except_candidate_id: int) -> list[int]:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT channel_message_id
                FROM card_image_review_candidates
                WHERE character_id=%s AND id<>%s
                  AND channel_message_id IS NOT NULL
                  AND status='superseded'
                """,
                (int(character_id), int(except_candidate_id)),
            )
            return [int(row[0]) for row in cur.fetchall() if row[0]]


async def _disable_superseded_buttons(context: ContextTypes.DEFAULT_TYPE, message_ids: list[int]) -> None:
    for message_id in message_ids:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=REVIEW_CHANNEL,
                message_id=int(message_id),
                reply_markup=None,
            )
        except Exception:
            logger.info("Could not remove superseded review keyboard message=%s", message_id)


def _reject(candidate_id: int, admin_id: int) -> tuple[dict[str, Any] | None, bool]:
    row = _candidate(candidate_id)
    if not row or row["status"] != "pending" or row["queue_status"] != "reviewing":
        return None, False
    exhausted_round = False
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE card_image_review_candidates SET status='rejected', reviewed_by=%s, reviewed_at=NOW() WHERE id=%s AND status='pending'", (int(admin_id), int(candidate_id)))
            if cur.rowcount != 1:
                conn.rollback()
                return None, False
            cur.execute("SELECT COUNT(*) AS total FROM card_image_review_candidates WHERE character_id=%s AND status='pending'", (int(row["character_id"]),))
            count_row = cur.fetchone()
            remaining = int((count_row.get("total") if isinstance(count_row, dict) else count_row[0]) or 0)
            if remaining == 0:
                next_status = "queued" if int(row["round_no"]) < MAX_ROUNDS else "exhausted"
                cur.execute("UPDATE card_image_review_queue SET status=%s, updated_at=NOW() WHERE character_id=%s", (next_status, int(row["character_id"])))
                exhausted_round = True
        conn.commit()
    return row, exhausted_round


async def image_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    if not is_admin(int(user.id)):
        await query.answer("Somente administradores podem avaliar.", show_alert=True)
        return
    match = re.fullmatch(r"imgrev:([ar]):(\d+)", str(query.data or ""))
    if not match:
        return
    action, raw_id = match.groups()
    candidate_id = int(raw_id)
    if action == "a":
        row = await asyncio.to_thread(_approve, candidate_id, int(user.id))
        if not row:
            await query.answer("Essa opção já foi avaliada.", show_alert=True)
            return
        await query.answer("Foto aprovada e aplicada.")
        await query.edit_message_caption(caption=(query.message.caption_html or query.message.caption or "") + f"\n\n✅ <b>APROVADA</b> por {html.escape(user.full_name)}", parse_mode="HTML")
        context.application.create_task(
            dispatch_next_character(context.application),
            name="next-card-image-review",
        )
        sibling_message_ids = await asyncio.to_thread(
            _candidate_message_ids,
            int(row["character_id"]),
            candidate_id,
        )
        await _disable_superseded_buttons(context, sibling_message_ids)
        return

    row, round_finished = await asyncio.to_thread(_reject, candidate_id, int(user.id))
    if not row:
        await query.answer("Essa opção já foi avaliada.", show_alert=True)
        return
    await query.answer("Opção rejeitada.")
    await query.edit_message_caption(caption=(query.message.caption_html or query.message.caption or "") + f"\n\n❌ <b>REJEITADA</b> por {html.escape(user.full_name)}", parse_mode="HTML")
    if round_finished:
        context.application.create_task(dispatch_next_character(context.application), name="retry-card-image-review")


async def review_photos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    if not is_admin(int(user.id)):
        await message.reply_text("❌ Você não tem permissão para usar esse comando.")
        return
    if not REVIEW_CHANNEL:
        await message.reply_text("❌ Configure CARD_IMAGE_REVIEW_CHANNEL ou CANAL_PEDIDOS.")
        return
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text(
            "Uso: /revisarfotos Naruto\n"
            "Também aceita o ID da obra ou /revisarfotos status."
        )
        return
    if query.casefold() == "status":
        counts = await asyncio.to_thread(_review_counts)
        if not counts:
            await message.reply_text("Ainda não há nenhuma revisão preparada.")
            return
        labels = {
            "queued": "na fila",
            "reviewing": "em avaliação",
            "approved": "aprovados",
            "protected": "preservados",
            "exhausted": "sem opção aprovada",
        }
        lines = [f"• {labels.get(status, status)}: {total}" for status, total in sorted(counts.items())]
        await message.reply_text("📊 Revisão de fotos\n" + "\n".join(lines))
        return
    anime = find_anime(query)
    if not anime:
        await message.reply_text("❌ Obra não encontrada nos cards.")
        return
    result = await asyncio.to_thread(seed_anime_review, int(anime["anime_id"]))
    await message.reply_text(
        f"✅ Revisão preparada para {anime['anime']}.\n"
        f"Na fila: {result['inserted']} · protegidos: {result['protected']} · total: {result['total']}"
    )
    context.application.create_task(dispatch_next_character(context.application), name="start-card-image-review")


async def card_image_review_worker(application) -> None:
    ensure_review_tables()
    for anime_id in AUTO_ANIME_IDS:
        try:
            recovered = await asyncio.to_thread(_recover_failed_deliveries, anime_id)
            if recovered:
                logger.info("Recovered failed image review deliveries anime=%s total=%s", anime_id, recovered)
            await asyncio.to_thread(seed_anime_review, anime_id)
        except Exception:
            logger.exception("Could not seed automatic card image review anime=%s", anime_id)
    while True:
        try:
            await dispatch_next_character(application)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Card image review worker failed")
        await asyncio.sleep(45)
