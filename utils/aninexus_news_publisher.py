from __future__ import annotations

import asyncio
import html
import io
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from psycopg.rows import dict_row
from telegram import InputFile
from telegram.error import Forbidden, RetryAfter

from database import pool
from utils.image_proxy import ImageProxyError, fetch_public_image


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


ANINEXUS_NEWS_ENABLED = _env_bool("ANINEXUS_NEWS_ENABLED", True)
ANINEXUS_NEWS_API_URL = (
    os.getenv("ANINEXUS_NEWS_API_URL", "https://aninexus.com.br/api/news").strip()
    or "https://aninexus.com.br/api/news"
)
ANINEXUS_NEWS_SITE_URL = (
    os.getenv("ANINEXUS_NEWS_SITE_URL", "https://aninexus.com.br").strip().rstrip("/")
    or "https://aninexus.com.br"
)
ANINEXUS_NEWS_CHANNEL = (
    os.getenv("ANINEXUS_NEWS_CHANNEL", "@AniNexus_Oficial").strip()
    or "@AniNexus_Oficial"
)
ANINEXUS_NEWS_INTERVAL_SECONDS = _env_int(
    "ANINEXUS_NEWS_INTERVAL_SECONDS", 60, 15, 3600
)
ANINEXUS_NEWS_FETCH_LIMIT = _env_int("ANINEXUS_NEWS_FETCH_LIMIT", 60, 1, 60)
ANINEXUS_NEWS_MAX_PER_CYCLE = _env_int(
    "ANINEXUS_NEWS_MAX_PER_CYCLE", 5, 1, 20
)
ANINEXUS_NEWS_SEND_EXISTING = _env_bool("ANINEXUS_NEWS_SEND_EXISTING", False)
ANINEXUS_NEWS_FALLBACK_IMAGE_URL = (
    os.getenv(
        "ANINEXUS_NEWS_FALLBACK_IMAGE_URL",
        "https://aninexus.com.br/assets/logo-512.png",
    ).strip()
    or "https://aninexus.com.br/assets/logo-512.png"
)

_TABLES_READY = False
_TABLES_LOCK = threading.Lock()
_WORKER_KEY = "aninexus-news-channel"
_IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS aninexus_news_posts (
    slug TEXT PRIMARY KEY,
    article_id TEXT,
    title TEXT NOT NULL,
    image_url TEXT NOT NULL DEFAULT '',
    article_url TEXT NOT NULL,
    source_published_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    telegram_message_id BIGINT,
    last_error TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_aninexus_news_posts_delivery
    ON aninexus_news_posts(status, next_attempt_at, source_published_at, first_seen_at);

CREATE TABLE IF NOT EXISTS aninexus_news_worker_state (
    worker_key TEXT PRIMARY KEY,
    initialized_at TIMESTAMPTZ,
    last_poll_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _clean_text(value: Any, maximum: int) -> str:
    return " ".join(str(value or "").split()).strip()[:maximum]


def _http_url(value: Any, *, base_url: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(urljoin(base_url.rstrip("/") + "/", raw))
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_news_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        records = payload.get("items")
    else:
        records = payload
    if not isinstance(records, list):
        raise ValueError("invalid_news_payload")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue

        slug = _clean_text(record.get("slug"), 180)
        title = _clean_text(record.get("title"), 300)
        if not slug or not title or slug in seen:
            continue
        seen.add(slug)

        encoded_slug = quote(slug, safe="-._~")
        published_at = _parse_datetime(
            record.get("last_source_update_at")
            or record.get("source_published_at")
            or record.get("published_at")
            or record.get("updated_at")
        )
        normalized.append(
            {
                "slug": slug,
                "article_id": _clean_text(record.get("id"), 200),
                "title": title,
                "image_url": _http_url(
                    record.get("image_url"), base_url=ANINEXUS_NEWS_SITE_URL
                ),
                "article_url": (
                    f"{ANINEXUS_NEWS_SITE_URL}/noticias/{encoded_slug}"
                ),
                "source_published_at": published_at,
            }
        )
    return normalized


def build_news_caption(item: dict[str, Any]) -> str:
    title = html.escape(_clean_text(item.get("title"), 300))
    article_url = html.escape(str(item.get("article_url") or ""), quote=True)
    return (
        f"📰 <b>{title}</b>\n\n"
        f'🔗 <a href="{article_url}">Ler notícia completa no AniNexus</a>'
    )


def ensure_aninexus_news_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return

    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_TABLE_SQL)
            conn.commit()
        _TABLES_READY = True


def _ingest_feed(items: list[dict[str, Any]]) -> dict[str, int | bool]:
    ensure_aninexus_news_tables()
    if not items:
        raise ValueError("empty_news_feed")

    inserted = 0
    baselined = 0
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO aninexus_news_worker_state(worker_key)
                VALUES (%s)
                ON CONFLICT (worker_key) DO NOTHING
                """,
                (_WORKER_KEY,),
            )
            cur.execute(
                """
                SELECT initialized_at
                FROM aninexus_news_worker_state
                WHERE worker_key = %s
                FOR UPDATE
                """,
                (_WORKER_KEY,),
            )
            state = cur.fetchone() or {}
            initialized = state.get("initialized_at") is not None
            initial_status = (
                "pending" if initialized or ANINEXUS_NEWS_SEND_EXISTING else "baseline"
            )

            for item in items:
                cur.execute(
                    """
                    INSERT INTO aninexus_news_posts(
                        slug,
                        article_id,
                        title,
                        image_url,
                        article_url,
                        source_published_at,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (slug) DO NOTHING
                    RETURNING slug
                    """,
                    (
                        item["slug"],
                        item["article_id"] or None,
                        item["title"],
                        item["image_url"],
                        item["article_url"],
                        item["source_published_at"],
                        initial_status,
                    ),
                )
                new_row = cur.fetchone()
                if new_row:
                    inserted += 1
                    if initial_status == "baseline":
                        baselined += 1
                    continue

                cur.execute(
                    """
                    UPDATE aninexus_news_posts
                    SET article_id = COALESCE(%s, article_id),
                        title = %s,
                        image_url = CASE WHEN %s <> '' THEN %s ELSE image_url END,
                        article_url = %s,
                        source_published_at = COALESCE(%s, source_published_at),
                        updated_at = NOW()
                    WHERE slug = %s
                    """,
                    (
                        item["article_id"] or None,
                        item["title"],
                        item["image_url"],
                        item["image_url"],
                        item["article_url"],
                        item["source_published_at"],
                        item["slug"],
                    ),
                )

            cur.execute(
                """
                UPDATE aninexus_news_worker_state
                SET initialized_at = COALESCE(initialized_at, NOW()),
                    last_poll_at = NOW(),
                    last_success_at = NOW(),
                    last_error = NULL,
                    updated_at = NOW()
                WHERE worker_key = %s
                """,
                (_WORKER_KEY,),
            )
        conn.commit()

    return {
        "initialized_now": not initialized,
        "inserted": inserted,
        "baselined": baselined,
        "queued": inserted - baselined,
    }


def _record_poll_error(error: str) -> None:
    ensure_aninexus_news_tables()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO aninexus_news_worker_state(
                    worker_key, last_poll_at, last_error, updated_at
                )
                VALUES (%s, NOW(), %s, NOW())
                ON CONFLICT (worker_key) DO UPDATE
                SET last_poll_at = NOW(),
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
                """,
                (_WORKER_KEY, _clean_text(error, 1000)),
            )
        conn.commit()


def _claim_pending() -> dict[str, Any] | None:
    ensure_aninexus_news_tables()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT slug
                    FROM aninexus_news_posts
                    WHERE (
                        status = 'pending' AND next_attempt_at <= NOW()
                    ) OR (
                        status = 'processing'
                        AND updated_at < NOW() - INTERVAL '10 minutes'
                    )
                    ORDER BY COALESCE(source_published_at, first_seen_at) ASC,
                             first_seen_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE aninexus_news_posts AS p
                SET status = 'processing',
                    attempts = attempts + 1,
                    updated_at = NOW()
                FROM picked
                WHERE p.slug = picked.slug
                RETURNING p.slug,
                          p.article_id,
                          p.title,
                          p.image_url,
                          p.article_url,
                          p.source_published_at,
                          p.attempts
                """
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def _mark_sent(slug: str, message_id: int) -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE aninexus_news_posts
                SET status = 'sent',
                    telegram_message_id = %s,
                    sent_at = NOW(),
                    updated_at = NOW(),
                    last_error = NULL
                WHERE slug = %s
                """,
                (int(message_id), str(slug)),
            )
        conn.commit()


def _mark_retry(slug: str, error: str, delay_seconds: float) -> None:
    delay = max(5, min(3600, int(float(delay_seconds))))
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE aninexus_news_posts
                SET status = 'pending',
                    next_attempt_at = NOW() + (%s * INTERVAL '1 second'),
                    last_error = %s,
                    updated_at = NOW()
                WHERE slug = %s
                """,
                (delay, _clean_text(error, 1000), str(slug)),
            )
        conn.commit()


def _retry_after_seconds(exc: RetryAfter) -> float:
    value = getattr(exc, "retry_after", 1)
    if isinstance(value, timedelta):
        return max(1.0, value.total_seconds())
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return 1.0


def _image_filename(media_type: str) -> str:
    suffix = {
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }.get(str(media_type or "").lower(), ".jpg")
    return f"aninexus-noticia{suffix}"


def _is_channel_permission_error(exc: Exception) -> bool:
    if isinstance(exc, Forbidden):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "not enough rights",
            "chat not found",
            "bot is not a member",
            "have no rights",
            "need administrator rights",
        )
    )


async def _upload_photo(app, image_url: str, caption: str):
    parsed = urlparse(image_url)
    headers = dict(_IMAGE_HEADERS)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    content, media_type, _ = await fetch_public_image(
        image_url,
        headers=headers,
        timeout=httpx.Timeout(20.0, connect=10.0),
    )
    photo = InputFile(
        io.BytesIO(content),
        filename=_image_filename(media_type),
    )
    return await app.bot.send_photo(
        chat_id=ANINEXUS_NEWS_CHANNEL,
        photo=photo,
        caption=caption,
        parse_mode="HTML",
    )


async def _send_news(app, item: dict[str, Any]):
    caption = build_news_caption(item)
    candidates: list[str] = []
    for candidate in (item.get("image_url"), ANINEXUS_NEWS_FALLBACK_IMAGE_URL):
        url = _http_url(candidate, base_url=ANINEXUS_NEWS_SITE_URL)
        if url and url not in candidates:
            candidates.append(url)

    errors: list[str] = []
    for image_url in candidates:
        try:
            return await app.bot.send_photo(
                chat_id=ANINEXUS_NEWS_CHANNEL,
                photo=image_url,
                caption=caption,
                parse_mode="HTML",
            )
        except RetryAfter:
            raise
        except Exception as exc:
            if _is_channel_permission_error(exc):
                raise
            errors.append(f"url:{type(exc).__name__}:{exc}")

        try:
            return await _upload_photo(app, image_url, caption)
        except RetryAfter:
            raise
        except Exception as exc:
            if _is_channel_permission_error(exc):
                raise
            code = str(exc) if isinstance(exc, ImageProxyError) else repr(exc)
            errors.append(f"upload:{type(exc).__name__}:{code}")

    raise RuntimeError("news_photo_delivery_failed | " + " | ".join(errors[-4:]))


async def _fetch_feed(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(
        ANINEXUS_NEWS_API_URL,
        params={"limit": ANINEXUS_NEWS_FETCH_LIMIT},
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
    )
    response.raise_for_status()
    return normalize_news_items(response.json())


async def _deliver_pending(app) -> int:
    delivered = 0
    for _ in range(ANINEXUS_NEWS_MAX_PER_CYCLE):
        item = await asyncio.to_thread(_claim_pending)
        if not item:
            break

        slug = str(item["slug"])
        attempts = max(1, int(item.get("attempts") or 1))
        try:
            message = await _send_news(app, item)
            await asyncio.to_thread(_mark_sent, slug, int(message.message_id))
            delivered += 1
            print(
                f"[aninexus-news] enviada slug={slug} message_id={message.message_id}",
                flush=True,
            )
            await asyncio.sleep(1.0)
        except RetryAfter as exc:
            delay = _retry_after_seconds(exc) + 1
            await asyncio.to_thread(_mark_retry, slug, repr(exc), delay)
            break
        except asyncio.CancelledError:
            await asyncio.to_thread(_mark_retry, slug, "worker_cancelled", 5)
            raise
        except Exception as exc:
            delay = min(3600, max(15, 2 ** min(attempts, 11)))
            await asyncio.to_thread(_mark_retry, slug, repr(exc), delay)
            print(
                f"[aninexus-news] falha slug={slug} "
                f"attempt={attempts} error={type(exc).__name__}: {exc}",
                flush=True,
            )
    return delivered


async def aninexus_news_worker(app) -> None:
    if not ANINEXUS_NEWS_ENABLED:
        print("[aninexus-news] worker desativado", flush=True)
        return

    await asyncio.to_thread(ensure_aninexus_news_tables)
    print(
        f"[aninexus-news] worker iniciado channel={ANINEXUS_NEWS_CHANNEL} "
        f"interval={ANINEXUS_NEWS_INTERVAL_SECONDS}s",
        flush=True,
    )

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
        headers={
            "User-Agent": "SourceBaltigo-AniNexus-News/1.0",
        },
    ) as client:
        while True:
            try:
                items = await _fetch_feed(client)
                result = await asyncio.to_thread(_ingest_feed, items)
                if result["initialized_now"]:
                    print(
                        f"[aninexus-news] base inicial registrada={result['baselined']} "
                        f"queued={result['queued']}",
                        flush=True,
                    )
                elif result["queued"]:
                    print(
                        f"[aninexus-news] novas noticias={result['queued']}",
                        flush=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                try:
                    await asyncio.to_thread(
                        _record_poll_error,
                        f"{type(exc).__name__}: {exc}",
                    )
                except Exception as state_exc:
                    print(
                        f"[aninexus-news] state-error {type(state_exc).__name__}: {state_exc}",
                        flush=True,
                    )
                print(
                    f"[aninexus-news] poll-error {type(exc).__name__}: {exc}",
                    flush=True,
                )

            try:
                await _deliver_pending(app)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    f"[aninexus-news] delivery-worker-error "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )

            await asyncio.sleep(ANINEXUS_NEWS_INTERVAL_SECONDS)
