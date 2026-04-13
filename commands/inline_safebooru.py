import html
import logging
import os
from typing import Any

import httpx
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultPhoto,
    InlineQueryResultsButton,
    Update,
)
from telegram.ext import ContextTypes

from database import create_or_get_user, get_user_status


logger = logging.getLogger(__name__)

SAFEBOORU_API_URL = os.getenv(
    "SAFEBOORU_API_URL",
    "https://safebooru.org/index.php",
).strip()

SAFEBOORU_POST_URL = os.getenv(
    "SAFEBOORU_POST_URL",
    "https://safebooru.org/index.php?page=post&s=view&id={post_id}",
).strip()

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
BOT_BRAND = os.getenv("BOT_BRAND", "Baltigo").strip() or "Baltigo"

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()

INLINE_SAFEBOORU_ENABLED = (
    os.getenv("INLINE_SAFEBOORU_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
)
INLINE_SAFEBOORU_ENFORCE_ACCESS = (
    os.getenv("INLINE_SAFEBOORU_ENFORCE_ACCESS", "1").strip().lower() not in {"0", "false", "no", "off"}
)

INLINE_SAFEBOORU_MIN_QUERY = max(1, int(os.getenv("INLINE_SAFEBOORU_MIN_QUERY", "2")))
INLINE_SAFEBOORU_LIMIT = max(1, min(50, int(os.getenv("INLINE_SAFEBOORU_LIMIT", "50"))))
INLINE_SAFEBOORU_CACHE_TIME = max(1, int(os.getenv("INLINE_SAFEBOORU_CACHE_TIME", "60")))

INLINE_SAFEBOORU_DEFAULT_TAGS = (
    os.getenv(
        "INLINE_SAFEBOORU_DEFAULT_TAGS",
        "rating:safe -video -webm -animated",
    ).strip()
)

HTTP_TIMEOUT = float(os.getenv("INLINE_SAFEBOORU_TIMEOUT", "12"))
HTTP_USER_AGENT = os.getenv(
    "INLINE_SAFEBOORU_USER_AGENT",
    f"Mozilla/5.0 ({BOT_BRAND} Inline SafeBooru)",
).strip()

BOT_PRIVATE_URL = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""
PM_START_PARAMETER = os.getenv("INLINE_SAFEBOORU_START_PARAMETER", "inline_safebooru").strip() or "inline_safebooru"


def _normalize_query(raw_query: str) -> str:
    q = (raw_query or "").strip()

    lowered = q.lower()
    for prefix in ("sb ", "safebooru ", "/sb ", "/safebooru "):
        if lowered.startswith(prefix):
            q = q[len(prefix):].strip()
            break

    q = " ".join(q.split())
    return q


def _build_query_candidates(query: str) -> list[str]:
    """
    Gera variações para pegar mais resultados.
    Ex.:
    - "zero two" -> ["zero_two", "zero two"]
    - "rem" -> ["rem"]
    """
    q = (query or "").strip()
    if not q:
        return []

    variants: list[str] = []

    underscored = q.replace(" ", "_")
    if underscored and underscored != q:
        variants.append(underscored)

    variants.append(q)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())

    return deduped


def _parse_offset(offset: str) -> int:
    try:
        page = int((offset or "0").strip())
        return max(0, page)
    except Exception:
        return 0


def _normalize_url(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    return raw


def _is_jpeg(url: str) -> bool:
    lowered = (url or "").lower()
    return lowered.endswith(".jpg") or lowered.endswith(".jpeg")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _trim_tags(tags: str, limit: int = 8) -> str:
    parts = [p for p in (tags or "").split() if p]
    return ", ".join(parts[:limit])


def _build_post_url(post_id: int) -> str:
    return SAFEBOORU_POST_URL.format(post_id=post_id)


def _pm_button(text: str) -> InlineQueryResultsButton | None:
    if not BOT_USERNAME:
        return None
    return InlineQueryResultsButton(text=text[:64], start_parameter=PM_START_PARAMETER[:64])


async def _is_in_required_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True

    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception:
        return False


async def _check_inline_access(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> tuple[bool, str]:
    if not INLINE_SAFEBOORU_ENFORCE_ACCESS:
        return True, ""

    try:
        create_or_get_user(user_id)
        st = get_user_status(user_id) or {}
    except Exception:
        logger.exception("Falha ao verificar status do usuario no inline safebooru.")
        return False, "Nao consegui validar seu acesso agora."

    if not st.get("terms_accepted"):
        return False, "Aceite os termos no privado antes de usar o inline."

    if st.get("terms_version") != TERMS_VERSION:
        return False, "Seus termos estao desatualizados. Reabra o bot no privado."

    ok = await _is_in_required_channel(context, user_id)
    if not ok:
        return False, "Entre no canal obrigatorio e depois use o inline novamente."

    return True, ""


def _pick_photo_url(post: dict) -> str:
    """
    Preferimos JPEG.
    Ordem:
    1) sample_url
    2) file_url
    3) preview_url (fallback para não perder tantos resultados)
    """
    sample_url = _normalize_url(post.get("sample_url"))
    file_url = _normalize_url(post.get("file_url"))
    preview_url = _normalize_url(post.get("preview_url"))

    if sample_url and _is_jpeg(sample_url):
        return sample_url

    if file_url and _is_jpeg(file_url):
        return file_url

    if preview_url and _is_jpeg(preview_url):
        return preview_url

    return ""


def _pick_thumb_url(post: dict, fallback_photo_url: str) -> str:
    preview_url = _normalize_url(post.get("preview_url"))
    sample_url = _normalize_url(post.get("sample_url"))

    if preview_url:
        return preview_url
    if sample_url:
        return sample_url
    return fallback_photo_url


def _build_caption(post: dict) -> str:
    post_id = _safe_int(post.get("id"))
    tags = html.escape(_trim_tags(str(post.get("tags") or ""), limit=10))
    width = _safe_int(post.get("width"))
    height = _safe_int(post.get("height"))

    lines = [f"<b>SafeBooru</b> · #{post_id}"]

    if tags:
        lines.append(f"🏷️ {tags}")

    if width > 0 and height > 0:
        lines.append(f"📐 {width}x{height}")

    return "\n".join(lines)[:1024]


def _build_description(post: dict) -> str:
    tags = _trim_tags(str(post.get("tags") or ""), limit=6)
    if not tags:
        return "Resultado SafeBooru"
    return tags[:256]


def _build_result(post: dict, idx: int) -> InlineQueryResultPhoto | None:
    post_id = _safe_int(post.get("id"))
    if post_id <= 0:
        return None

    photo_url = _pick_photo_url(post)
    if not photo_url:
        return None

    thumb_url = _pick_thumb_url(post, photo_url)
    title = f"SafeBooru #{post_id}"
    description = _build_description(post)
    caption = _build_caption(post)
    post_url = _build_post_url(post_id)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔎 Ver no SafeBooru", url=post_url)],
        ]
    )

    return InlineQueryResultPhoto(
        id=f"sb_{post_id}_{idx}"[:64],
        photo_url=photo_url,
        thumbnail_url=thumb_url,
        title=title[:64],
        description=description[:256],
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard,
        photo_width=_safe_int(post.get("width"), 0) or None,
        photo_height=_safe_int(post.get("height"), 0) or None,
    )


async def _fetch_posts_once(tags: str, page: int) -> list[dict]:
    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": "1",
        "limit": str(INLINE_SAFEBOORU_LIMIT),
        "pid": str(max(0, page)),
        "tags": " ".join(
            part for part in [INLINE_SAFEBOORU_DEFAULT_TAGS, tags] if part
        ).strip(),
    }

    headers = {
        "User-Agent": HTTP_USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://safebooru.org/",
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(SAFEBOORU_API_URL, params=params, headers=headers)
        resp.raise_for_status()

        data = resp.json()

        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        if isinstance(data, dict) and isinstance(data.get("posts"), list):
            return [x for x in data["posts"] if isinstance(x, dict)]

        return []


async def _search_posts(query: str, page: int) -> tuple[list[dict], bool]:
    """
    Busca em mais de uma variação da query e junta sem duplicar.
    Retorna:
    - lista de posts
    - has_more
    """
    candidates = _build_query_candidates(query)
    merged: list[dict] = []
    seen_ids: set[int] = set()
    has_more = False

    for candidate in candidates:
        posts = await _fetch_posts_once(candidate, page)

        if len(posts) >= INLINE_SAFEBOORU_LIMIT:
            has_more = True

        for post in posts:
            post_id = _safe_int(post.get("id"))
            if post_id <= 0 or post_id in seen_ids:
                continue

            seen_ids.add(post_id)
            merged.append(post)

            if len(merged) >= INLINE_SAFEBOORU_LIMIT:
                return merged, has_more

    return merged, has_more


async def _answer_empty(
    update: Update,
    text_button: str = "Abrir bot no privado",
    cache_time: int = 1,
) -> None:
    inline_query = update.inline_query
    if not inline_query:
        return

    await inline_query.answer(
        results=[],
        cache_time=cache_time,
        is_personal=True,
        next_offset="",
        button=_pm_button(text_button),
    )


async def safebooru_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    inline_query = update.inline_query
    if not inline_query:
        return

    if not INLINE_SAFEBOORU_ENABLED:
        await _answer_empty(update, text_button="Inline desativado", cache_time=3)
        return

    user = inline_query.from_user
    if not user:
        await _answer_empty(update, text_button="Abrir bot", cache_time=1)
        return

    access_ok, reason = await _check_inline_access(context, user.id)
    if not access_ok:
        logger.info("Inline SafeBooru bloqueado para user_id=%s: %s", user.id, reason)
        await _answer_empty(update, text_button="Liberar acesso no privado", cache_time=1)
        return

    query = _normalize_query(inline_query.query)

    if len(query) < INLINE_SAFEBOORU_MIN_QUERY:
        await _answer_empty(update, text_button="Pesquisar no privado", cache_time=1)
        return

    page = _parse_offset(inline_query.offset)

    try:
        posts, has_more = await _search_posts(query, page)
    except Exception:
        logger.exception("Falha buscando SafeBooru no inline.")
        await inline_query.answer(
            results=[],
            cache_time=3,
            is_personal=True,
            next_offset="",
            button=_pm_button("Abrir bot"),
        )
        return

    results: list[InlineQueryResultPhoto] = []
    seen_ids: set[int] = set()

    for idx, post in enumerate(posts):
        post_id = _safe_int(post.get("id"))
        if post_id <= 0 or post_id in seen_ids:
            continue

        result = _build_result(post, idx)
        if not result:
            continue

        seen_ids.add(post_id)
        results.append(result)

        if len(results) >= INLINE_SAFEBOORU_LIMIT:
            break

    next_offset = str(page + 1) if has_more and results else ""

    await inline_query.answer(
        results=results,
        cache_time=INLINE_SAFEBOORU_CACHE_TIME,
        is_personal=True,
        next_offset=next_offset,
        button=_pm_button("Abrir bot no privado"),
    )
