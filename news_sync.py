from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from psycopg.rows import dict_row

from database import pool
from ecosystem_repository import push_notification

logger = logging.getLogger(__name__)

NEWS_RSS_FEEDS = [item.strip() for item in os.getenv("NEWS_RSS_FEEDS", "").split(",") if item.strip()]
NEWS_SYNC_SECONDS = max(900, int(os.getenv("NEWS_SYNC_SECONDS", "3600")))
NEWS_MAX_PER_FEED = max(5, min(100, int(os.getenv("NEWS_MAX_PER_FEED", "30"))))


def _text(node: ET.Element | None, *names: str) -> str:
    if node is None:
        return ""
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _clean_summary(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())[:700]


def _parse_date(value: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[dict[str, Any]] = []
    for node in root.findall(".//item"):
        title = _text(node, "title")
        link = _text(node, "link")
        if not link:
            guid = _text(node, "guid")
            link = guid if guid.startswith("http") else ""
        if not title or not link:
            continue
        items.append({
            "title": title[:260],
            "summary": _clean_summary(_text(node, "description", "summary", "content")),
            "source_url": link[:2000],
            "published_at": _parse_date(_text(node, "pubDate", "published", "updated")),
        })
    if items:
        return items
    for node in root.iter():
        if node.tag.split("}")[-1] != "entry":
            continue
        title = ""; summary = ""; link = ""; published = ""
        for child in list(node):
            name = child.tag.split("}")[-1]
            if name == "title" and child.text:
                title = child.text.strip()
            elif name in {"summary", "content"} and child.text:
                summary = child.text.strip()
            elif name in {"published", "updated"} and child.text and not published:
                published = child.text.strip()
            elif name == "link":
                href = child.attrib.get("href", "")
                if href and (child.attrib.get("rel", "alternate") == "alternate" or not link):
                    link = href
        if title and link:
            items.append({"title": title[:260], "summary": _clean_summary(summary), "source_url": link[:2000], "published_at": _parse_date(published)})
    return items


def _notify_followers(article_id: int, title: str, summary: str, source_url: str) -> None:
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT DISTINCT l.user_id, l.title
                FROM user_library_v2 l
                WHERE (l.is_favorite=TRUE OR l.status IN ('planned','watching'))
                  AND LENGTH(BTRIM(l.title)) >= 4
                  AND LOWER(%s) LIKE '%%' || LOWER(BTRIM(l.title)) || '%%'
                LIMIT 500
                """,
                (str(title),),
            )
            followers = [dict(row) for row in (cur.fetchall() or [])]
    for row in followers:
        push_notification(
            int(row["user_id"]), "news", f"📰 {title[:150]}", summary[:400], "/hub#explore",
            {"news_id": int(article_id), "source_url": source_url, "matched_title": row.get("title")},
        )


def ingest_articles(articles: list[dict[str, Any]]) -> int:
    inserted: list[dict[str, Any]] = []
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                for article in articles:
                    source_url = str(article.get("source_url") or "").strip()
                    if not source_url:
                        continue
                    # An advisory lock derived by PostgreSQL guarantees that two workers
                    # cannot ingest the same URL at once even before a formal migration
                    # introduces a unique index.
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (source_url,))
                    cur.execute("SELECT id FROM news_items_v2 WHERE source_url=%s LIMIT 1", (source_url,))
                    if cur.fetchone():
                        continue
                    cur.execute(
                        """
                        INSERT INTO news_items_v2 (title,summary,source_url,published_at)
                        VALUES (%s,%s,%s,%s)
                        RETURNING id,title,summary,source_url
                        """,
                        (
                            str(article.get("title") or "Notícia")[:260],
                            str(article.get("summary") or "")[:700],
                            source_url[:2000],
                            article.get("published_at") or datetime.now(timezone.utc),
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        inserted.append(dict(row))
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("Falha transacional ao inserir notícias")
                return 0
    for row in inserted:
        try:
            _notify_followers(int(row["id"]), str(row["title"]), str(row.get("summary") or ""), str(row.get("source_url") or ""))
        except Exception:
            logger.exception("Falha ao notificar seguidores news_id=%s", row.get("id"))
    return len(inserted)


async def sync_news_once() -> int:
    if not NEWS_RSS_FEEDS:
        return 0
    total = 0
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={"User-Agent": "SourceBaltigo/2.0"}) as client:
        for feed_url in NEWS_RSS_FEEDS:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()
                total += ingest_articles(parse_feed(response.text)[:NEWS_MAX_PER_FEED])
            except Exception:
                logger.exception("Falha no feed de notícias %s", feed_url)
    return total


async def news_worker() -> None:
    while True:
        try:
            await sync_news_once()
        except Exception:
            logger.exception("Falha inesperada no sincronizador de notícias")
        await asyncio.sleep(NEWS_SYNC_SECONDS)


def start_news_worker() -> asyncio.Task | None:
    if not NEWS_RSS_FEEDS:
        logger.info("News sync desativado: NEWS_RSS_FEEDS vazio")
        return None
    return asyncio.create_task(news_worker(), name="baltigo-news-sync")
