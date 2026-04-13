import html
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

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

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
BOT_BRAND = os.getenv("BOT_BRAND", "Baltigo").strip() or "Baltigo"

TERMS_VERSION = os.getenv("TERMS_VERSION", "v1").strip() or "v1"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()

ANILIST_API_URL = os.getenv("ANILIST_API_URL", "https://graphql.anilist.co").strip()
ANILIST_CACHE_TTL = max(60, int(os.getenv("INLINE_SAFEBOORU_ANILIST_CACHE_TTL", "21600")))

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

PM_START_PARAMETER = os.getenv("INLINE_SAFEBOORU_START_PARAMETER", "inline_safebooru").strip() or "inline_safebooru"

_ANILIST_CACHE: dict[str, tuple[float, dict | None]] = {}

_SOURCE_URL_RE = re.compile(
    r"(https?://[^\s<>\"]+|(?:x\.com|twitter\.com|pixiv\.net|www\.[^\s<>\"]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s<>\"]+))"
)


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

    if raw.startswith(("x.com/", "twitter.com/", "www.", "pixiv.net/")):
        return f"https://{raw}"

    if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/", raw):
        return f"https://{raw}"

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
    Prioriza qualidade maior:
    1) file_url
    2) sample_url
    3) preview_url
    """
    file_url = _normalize_url(post.get("file_url"))
    sample_url = _normalize_url(post.get("sample_url"))
    preview_url = _normalize_url(post.get("preview_url"))

    if file_url and _is_jpeg(file_url):
        return file_url

    if sample_url and _is_jpeg(sample_url):
        return sample_url

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


def _extract_source_url(post: dict) -> str:
    raw = str(post.get("source") or "").strip()
    if not raw:
        return ""

    match = _SOURCE_URL_RE.search(raw)
    if not match:
        return ""

    url = _normalize_url(match.group(1).strip())
    return url.rstrip(".,);]")


def _source_button_text(source_url: str) -> str:
    if not source_url:
        return ""

    try:
        parsed = urlparse(source_url)
        host = (parsed.netloc or "").replace("www.", "")
        path = (parsed.path or "").strip("/")
        if path:
            display = f"{host}/{path}"
        else:
            display = host or source_url
    except Exception:
        display = source_url

    display = display[:42]
    return f"Source: {display}"[:64]


def _build_reply_markup(post: dict) -> InlineKeyboardMarkup | None:
    source_url = _extract_source_url(post)
    if not source_url:
        return None

    text = _source_button_text(source_url)
    if not text:
        return None

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, url=source_url)]]
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


def _pick_title(title_obj: dict | None) -> str:
    if not isinstance(title_obj, dict):
        return ""
    return (
        str(title_obj.get("english") or "").strip()
        or str(title_obj.get("romaji") or "").strip()
        or str(title_obj.get("native") or "").strip()
        or str(title_obj.get("userPreferred") or "").strip()
    )


def _fmt_birth(day: int | None, month: int | None) -> str:
    if day and month:
        return f"{day}/{month}"
    if month:
        return f"{month}"
    return "—"


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return html.escape(text) if text else "—"


async def _fetch_anilist_character(search: str) -> dict | None:
    key = (search or "").strip().lower()
    if not key:
        return None

    now = time.time()
    cached = _ANILIST_CACHE.get(key)
    if cached and (now - cached[0]) < ANILIST_CACHE_TTL:
        return cached[1]

    query = """
    query CharacterSearch($search: String) {
      Page(page: 1, perPage: 1) {
        characters(search: $search) {
          id
          name {
            full
            userPreferred
            native
          }
          gender
          favourites
          dateOfBirth {
            day
            month
          }
          siteUrl
          media(page: 1, perPage: 1, sort: [POPULARITY_DESC]) {
            edges {
              characterRole
              node {
                type
                format
                startDate {
                  year
                }
                title {
                  english
                  romaji
                  native
                  userPreferred
                }
              }
            }
          }
        }
      }
    }
    """

    payload = {
        "query": query,
        "variables": {"search": search},
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": HTTP_USER_AGENT,
    }

    result: dict | None = None

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.post(ANILIST_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        characters = (
            data.get("data", {})
            .get("Page", {})
            .get("characters", [])
        )

        if characters:
            ch = characters[0]
            media_edges = (ch.get("media") or {}).get("edges") or []
            first_edge = media_edges[0] if media_edges else {}
            media_node = first_edge.get("node") or {}

            result = {
                "name": (
                    (ch.get("name") or {}).get("full")
                    or (ch.get("name") or {}).get("userPreferred")
                    or (ch.get("name") or {}).get("native")
                    or search
                ),
                "gender": ch.get("gender") or "—",
                "favourites": ch.get("favourites") or "—",
                "birth_day": ((ch.get("dateOfBirth") or {}).get("day")),
                "birth_month": ((ch.get("dateOfBirth") or {}).get("month")),
                "media_title": _pick_title(media_node.get("title")),
                "media_type": media_node.get("type") or "—",
                "media_format": media_node.get("format") or "—",
                "role": first_edge.get("characterRole") or "—",
                "year": ((media_node.get("startDate") or {}).get("year")) or "—",
                "site_url": ch.get("siteUrl") or "",
            }
    except Exception:
        logger.exception("Falha buscando personagem no AniList: %s", search)

    _ANILIST_CACHE[key] = (now, result)
    return result


def _build_caption_from_anilist(query: str, meta: dict | None, post: dict) -> str:
    if meta:
        name = _clean_text(meta.get("name"))
        gender = _clean_text(meta.get("gender"))
        birth = _clean_text(_fmt_birth(meta.get("birth_day"), meta.get("birth_month")))
        favourites = _clean_text(meta.get("favourites"))
        media_title = _clean_text(meta.get("media_title"))
        media_type = _clean_text(meta.get("media_type"))
        role = _clean_text(meta.get("role"))
        year = _clean_text(meta.get("year"))

        lines = [
            f"<b>{name}</b>",
            "",
            f"Gênero: <code>{gender}</code>",
            f"Nascimento: <code>{birth}</code>",
            f"Favoritos: <code>{favourites}</code>",
            "",
            f"Obra: <code>{media_title}</code>",
            f"Tipo: <code>{media_type}</code>",
            f"Papel: <code>{role}</code>",
            f"Ano: <code>{year}</code>",
        ]
        return "\n".join(lines)[:1024]

    # fallback elegante
    clean_query = _clean_text(query.title())
    tags = _clean_text(_trim_tags(str(post.get("tags") or ""), limit=8))
    return (
        f"<b>{clean_query}</b>\n\n"
        f"Tags: <code>{tags}</code>"
    )[:1024]


def _build_description_from_anilist(meta: dict | None, query: str) -> str:
    if meta:
        media_title = str(meta.get("media_title") or "").strip()
        role = str(meta.get("role") or "").strip()
        year = str(meta.get("year") or "").strip()

        bits = [b for b in [media_title, role, year] if b and b != "—"]
        if bits:
            return " • ".join(bits)[:256]

    return query[:256]


def _build_result(
    post: dict,
    idx: int,
    query: str,
    anilist_meta: dict | None,
) -> InlineQueryResultPhoto | None:
    post_id = _safe_int(post.get("id"))
    if post_id <= 0:
        return None

    photo_url = _pick_photo_url(post)
    if not photo_url:
        return None

    thumb_url = _pick_thumb_url(post, photo_url)
    title = str((anilist_meta or {}).get("name") or query or f"SafeBooru #{post_id}").strip()
    description = _build_description_from_anilist(anilist_meta, query)
    caption = _build_caption_from_anilist(query, anilist_meta, post)
    reply_markup = _build_reply_markup(post)

    return InlineQueryResultPhoto(
        id=f"sb_{post_id}_{idx}"[:64],
        photo_url=photo_url,
        thumbnail_url=thumb_url,
        title=title[:64],
        description=description[:256],
        caption=caption,
        parse_mode="HTML",
        reply_markup=reply_markup,
        photo_width=_safe_int(post.get("width"), 0) or None,
        photo_height=_safe_int(post.get("height"), 0) or None,
    )


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

    # AniList usa a query limpa, com espaço humano
    anilist_query = query.replace("_", " ").strip()
    anilist_meta = await _fetch_anilist_character(anilist_query)

    results: list[InlineQueryResultPhoto] = []
    seen_ids: set[int] = set()

    for idx, post in enumerate(posts):
        post_id = _safe_int(post.get("id"))
        if post_id <= 0 or post_id in seen_ids:
            continue

        result = _build_result(
            post=post,
            idx=idx,
            query=anilist_query,
            anilist_meta=anilist_meta,
        )
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
