import asyncio
import re
import time
import unicodedata
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from core.http_client import get_http_client

import random
from urllib.parse import quote

BASE_URL = "https://animefire.io"
ANILIST_API_URL = "https://graphql.anilist.co"

LIGHTSPEED_SERVERS = ["s6", "s7", "s5", "s4", "s8", "s3", "s2", "s1", "s9"]

_SEARCH_CACHE = {}
_DETAILS_CACHE = {}
_EPISODES_CACHE = {}
_VIDEO_CACHE = {}
_ANILIST_CACHE = {}

_SEARCH_CACHE_TTL = 1800
_DETAILS_CACHE_TTL = 21600
_EPISODES_CACHE_TTL = 1800
_VIDEO_CACHE_TTL = 21600
_ANILIST_CACHE_TTL = 86400

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": BASE_URL,
}

_ANILIST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _cache_get(cache: dict, key: str, ttl: int):
    item = cache.get(key)
    if not item:
        return None

    if time.time() - item["time"] > ttl:
        cache.pop(key, None)
        return None

    return item["data"]


def _cache_set(cache: dict, key: str, data):
    cache[key] = {
        "time": time.time(),
        "data": data,
    }


async def _get(url: str) -> str:
    client = await get_http_client()
    r = await client.get(url, headers=_HTTP_HEADERS)
    r.raise_for_status()
    return r.text


async def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    merged_headers = dict(_ANILIST_HEADERS)
    if headers:
        merged_headers.update(headers)

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
    ) as client:
        r = await client.post(
            url,
            json=payload,
            headers=merged_headers,
        )
        r.raise_for_status()
        return r.json()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _normalize_slug_for_page(anime_id: str) -> str:
    return (anime_id or "").strip().strip("/")


def _normalize_episode_slug(slug: str) -> str:
    slug = (slug or "").strip().strip("/")
    slug = slug.replace("-todos-os-episodios", "")
    return slug


def _normalize_text(text: str) -> str:
    text = (text or "").lower().strip()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _search_path_term(query: str) -> str:
    text = _normalize_text(query)
    text = text.replace(" ", "-")
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _extract_server_name(url: str) -> str:
    if "blogger.com/video.g" in (url or ""):
        return "BLOGGER"

    if "googlevideo.com" in (url or ""):
        return "GOOGLEVIDEO"

    m = re.search(r"lightspeedst\.net/(s\d+)", url or "")
    return m.group(1).upper() if m else "S6"


def _extract_quality_name(url: str) -> str:
    url = (url or "").lower()

    if "fmt=37" in url or "1080p" in url:
        return "FULLHD"
    if "fmt=22" in url or "720p" in url or "/hd/" in url:
        return "HD"
    if "fmt=18" in url or "480p" in url or "/sd/" in url:
        return "SD"
    if "blogger.com/video.g" in url:
        return "HD"

    return "HD"


def _normalize_quality_label(value: str) -> str:
    value = (value or "").upper().strip()

    if value in {"FULLHD", "FHD", "1080P"}:
        return "FULLHD"
    if value in {"HD", "720P"}:
        return "HD"
    if value in {"SD", "480P", "360P"}:
        return "SD"

    return ""


def _extract_local_genres(soup: BeautifulSoup) -> list[str]:
    genres = []
    seen = set()

    for a in soup.select("a[href*='/genero/']"):
        text = _clean(a.get_text(" ", strip=True))
        if not text:
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        genres.append(text)

    return genres


def _score_candidate(query: str, title: str, slug: str) -> float:
    q = _normalize_text(query)
    t = _normalize_text(title)
    s = _normalize_text(slug.replace("-", " "))

    if not q:
        return -9999

    q_words = [w for w in q.split() if len(w) > 1]
    if not q_words:
        return -9999

    score = 0.0

    if q == t:
        score += 1000
    if q == s:
        score += 900
    if q in t:
        score += 500
    if q in s:
        score += 350

    if len(q_words) == 1:
        w = q_words[0]
        if w not in t and w not in s:
            return -9999

        if t.startswith(w):
            score += 120
        if s.startswith(w):
            score += 90
    else:
        for w in q_words:
            if w not in t and w not in s:
                return -9999

    for w in q_words:
        if w in t:
            score += 80
        if w in s:
            score += 45

    if "episodio" in t or "episódio" in t:
        score -= 500

    score += max(0, 50 - len(t))
    return score


def _best_title_from_anilist(media: dict) -> str:
    title = media.get("title") or {}
    return (
        title.get("userPreferred")
        or title.get("romaji")
        or title.get("english")
        or title.get("native")
        or "Sem título"
    )


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def _anilist_status_label(status: str) -> str:
    mapping = {
        "FINISHED": "Finalizado",
        "RELEASING": "Em lançamento",
        "NOT_YET_RELEASED": "Não lançado",
        "CANCELLED": "Cancelado",
        "HIATUS": "Em hiato",
    }
    return mapping.get((status or "").upper(), status or "")


def _anilist_format_label(fmt: str) -> str:
    mapping = {
        "TV": "TV",
        "TV_SHORT": "TV Short",
        "MOVIE": "Filme",
        "SPECIAL": "Especial",
        "OVA": "OVA",
        "ONA": "ONA",
        "MUSIC": "Music",
    }
    return mapping.get((fmt or "").upper(), fmt or "")


def _is_bad_description(text: str) -> bool:
    text = (text or "").strip().lower()
    if not text:
        return True

    bad_fragments = [
        "este site não hospeda nenhum vídeo em seu servidor",
        "todo conteúdo é provido de terceiros",
        "conteúdo é provido de terceiros",
        "assista",
        "baixar",
    ]

    return any(fragment in text for fragment in bad_fragments)


def _extract_description_from_page(soup: BeautifulSoup) -> str:
    text = soup.get_text("\n", strip=True)

    m = re.search(
        r"Sinopse:\s*(.+?)(?:\n[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{0,60}:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        description = _clean(m.group(1))
        if description and not _is_bad_description(description):
            return description

    paragraphs = []
    for p in soup.find_all("p"):
        candidate = _clean(p.get_text(" ", strip=True))
        if len(candidate) >= 80 and not _is_bad_description(candidate):
            paragraphs.append(candidate)

    if paragraphs:
        paragraphs.sort(key=len, reverse=True)
        return paragraphs[0]

    return ""


def _extract_blogger_iframe(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for iframe in soup.find_all("iframe"):
        src = (iframe.get("src") or "").strip()
        if "blogger.com/video.g" in src:
            return src

    m = re.search(r'https://www\.blogger\.com/video\.g\?token=[^"\']+', html)
    if m:
        return m.group(0)

    return ""


def _extract_googlevideo_url(html: str) -> str:
    m = re.search(r'https://[^"\']*googlevideo\.com/videoplayback[^"\']+', html)
    if m:
        return m.group(0)
    return ""


async def _get_episode_page_html(base_slug: str, episode: str) -> str:
    safe_slug = _normalize_episode_slug(base_slug)
    url = f"{BASE_URL}/animes/{safe_slug}/{episode}"
    return await _get(url)


def _merge_anime_data(local_data: dict, anilist_data: dict | None) -> dict:
    if not anilist_data:
        return local_data

    merged = dict(local_data)

    local_description = (local_data.get("description") or "").strip()
    anilist_description = (anilist_data.get("description") or "").strip()

    if not local_description and anilist_description:
        merged["description"] = anilist_description

    if anilist_data.get("cover_url"):
        merged["cover_url"] = anilist_data["cover_url"]

    if anilist_data.get("banner_url"):
        merged["banner_url"] = anilist_data["banner_url"]

    for key in (
        "score",
        "status",
        "format",
        "episodes",
        "season",
        "season_year",
        "genres",
        "studio",
        "anilist_id",
        "anilist_url",
        "title_romaji",
        "title_english",
        "title_native",
        "media_image_url",
        "trailer_id",
        "trailer_site",
    ):
        if anilist_data.get(key) not in (None, "", []):
            merged[key] = anilist_data[key]

    return merged


async def _search_anilist_by_title(title: str) -> dict | None:
    cache_key = _normalize_text(title)
    if not cache_key:
        return None

    cached = _cache_get(_ANILIST_CACHE, cache_key, _ANILIST_CACHE_TTL)
    if cached is not None:
        return cached

    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        id
        siteUrl
        title {
          romaji
          english
          native
          userPreferred
        }
        description(asHtml: false)
        averageScore
        status
        format
        episodes
        season
        seasonYear
        genres
        bannerImage
        trailer {
          site
          id
        }
        coverImage {
          extraLarge
          large
          medium
        }
        studios(isMain: true) {
          nodes {
            name
          }
        }
      }
    }
    """

    payload = {
        "query": query,
        "variables": {
            "search": title,
        },
    }

    try:
        data = await _post_json(ANILIST_API_URL, payload, headers=_ANILIST_HEADERS)
        media = ((data or {}).get("data") or {}).get("Media")
        if not media:
            _cache_set(_ANILIST_CACHE, cache_key, None)
            return None

        studios = (((media.get("studios") or {}).get("nodes")) or [])
        studio_name = studios[0].get("name") if studios else ""

        description = _clean(_strip_html_tags(media.get("description") or ""))

        item = {
            "anilist_id": media.get("id"),
            "anilist_url": media.get("siteUrl") or "",
            "title_romaji": ((media.get("title") or {}).get("romaji")) or "",
            "title_english": ((media.get("title") or {}).get("english")) or "",
            "title_native": ((media.get("title") or {}).get("native")) or "",
            "title": _best_title_from_anilist(media),
            "description": description,
            "score": media.get("averageScore"),
            "status": _anilist_status_label(media.get("status") or ""),
            "format": _anilist_format_label(media.get("format") or ""),
            "episodes": media.get("episodes"),
            "season": (media.get("season") or ""),
            "season_year": media.get("seasonYear"),
            "genres": media.get("genres") or [],
            "studio": studio_name,
            "banner_url": media.get("bannerImage") or "",
            "cover_url": (
                ((media.get("coverImage") or {}).get("extraLarge"))
                or ((media.get("coverImage") or {}).get("large"))
                or ((media.get("coverImage") or {}).get("medium"))
                or ""
            ),
            "media_image_url": f"https://img.anili.st/media/{media.get('id')}" if media.get("id") else "",
            "trailer_id": ((media.get("trailer") or {}).get("id")) or "",
            "trailer_site": ((media.get("trailer") or {}).get("site")) or "",
        }

        _cache_set(_ANILIST_CACHE, cache_key, item)
        return item
    except Exception as e:
        print(f"[ANILIST] erro_na_busca={repr(e)}")
        _cache_set(_ANILIST_CACHE, cache_key, None)
        return None


async def search_anime(query: str):
    key = (query or "").strip().lower()

    cached = _cache_get(_SEARCH_CACHE, key, _SEARCH_CACHE_TTL)
    if cached is not None:
        return cached

    search_term = _search_path_term(query)
    url = f"{BASE_URL}/pesquisar/{quote(search_term)}"

    try:
        html = await _get(url)
    except Exception as e:
        print(f"[BUSCA] erro_no_get={repr(e)}")
        raise

    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("a[href*='/animes/']")

    found = {}

    for a in links:
        href = (a.get("href") or "").strip()
        if "/animes/" not in href:
            continue

        slug = href.split("/animes/")[-1].strip("/")
        if not slug or "/" in slug:
            continue

        title = _clean(a.get_text())
        if not title:
            img = a.find("img")
            if img:
                title = _clean(img.get("alt"))

        if not title:
            title = slug.replace("-", " ").title()

        score = _score_candidate(query, title, slug)
        if score <= -9999:
            continue

        item = {
            "id": slug,
            "title": title,
            "_score": score,
        }

        prev = found.get(slug)
        if not prev or item["_score"] > prev["_score"]:
            found[slug] = item

    ordered = sorted(found.values(), key=lambda x: (-x["_score"], x["title"].lower()))
    results = [{"id": x["id"], "title": x["title"]} for x in ordered[:20]]

    _cache_set(_SEARCH_CACHE, key, results)
    return results


async def get_anime_details(anime_id: str):
    anime_id = _normalize_slug_for_page(anime_id)

    cached = _cache_get(_DETAILS_CACHE, anime_id, _DETAILS_CACHE_TTL)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/animes/{anime_id}"
    html = await _get(url)
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else anime_id.replace("-", " ").title()

    description = _extract_description_from_page(soup)

    cover_url = ""
    og_img = soup.find("meta", attrs={"property": "og:image"})
    if og_img and og_img.get("content"):
        cover_url = og_img["content"].strip()

    if not cover_url:
        img = soup.find("img")
        if img and img.get("src"):
            cover_url = img["src"].strip()

    local_genres = _extract_local_genres(soup)

    local_data = {
        "id": anime_id,
        "title": title,
        "description": description,
        "url": url,
        "cover_url": cover_url,
        "banner_url": "",
        "media_image_url": "",
        "score": None,
        "status": "",
        "format": "",
        "episodes": None,
        "season": "",
        "season_year": None,
        "genres": local_genres,
        "studio": "",
        "anilist_id": None,
        "anilist_url": "",
        "title_romaji": "",
        "title_english": "",
        "title_native": "",
        "trailer_id": "",
        "trailer_site": "",
    }

    anilist_data = await _search_anilist_by_title(title)
    data = _merge_anime_data(local_data, anilist_data)

    _cache_set(_DETAILS_CACHE, anime_id, data)
    return data


async def get_episodes(anime_id: str, offset: int = 0, limit: int = 3000):
    anime_id = _normalize_slug_for_page(anime_id)

    cached = _cache_get(_EPISODES_CACHE, anime_id, _EPISODES_CACHE_TTL)
    if cached is None:
        url = f"{BASE_URL}/animes/{anime_id}"
        html = await _get(url)
        soup = BeautifulSoup(html, "html.parser")

        episodes = []
        pattern = re.compile(r"/animes/([^/]+)/(\d+)(?:/)?$")

        for a in soup.select("a[href*='/animes/']"):
            href = (a.get("href") or "").strip()
            m = pattern.search(href)
            if not m:
                continue

            base_slug = m.group(1)
            ep = m.group(2)

            episodes.append({
                "episode": ep,
                "base_slug": base_slug,
            })

        unique = {}
        for e in episodes:
            unique[e["episode"]] = e

        items = sorted(unique.values(), key=lambda x: int(x["episode"]))
        _cache_set(_EPISODES_CACHE, anime_id, items)
        cached = items

    items = cached
    total = len(items)
    page = items[offset: offset + limit]

    return {
        "items": page,
        "total": total,
    }


async def _url_exists_with_client(client, url: str) -> bool:
    try:
        r = await client.head(url)
        if r.status_code == 200:
            content_type = (r.headers.get("content-type") or "").lower()
            if "video" in content_type or "mp4" in content_type or content_type == "":
                return True
    except Exception:
        pass

    try:
        r = await client.get(url, headers={"Range": "bytes=0-0"})
        if r.status_code in (200, 206):
            content_type = (r.headers.get("content-type") or "").lower()
            if (
                "video" in content_type
                or "mp4" in content_type
                or "octet-stream" in content_type
                or "text/html" in content_type
            ):
                return True
    except Exception:
        pass

    return False


async def _check_candidate(url: str):
    client = await get_http_client()
    ok = await _url_exists_with_client(client, url)
    return url if ok else None


def _build_candidate_urls(base_slug: str, episode: str):
    qualities = {
        "FULLHD": [],
        "HD": [],
        "SD": [],
    }

    for server in LIGHTSPEED_SERVERS:
        base = f"https://lightspeedst.net/{server}"

        qualities["FULLHD"].append(
            f"{base}/mp4_temp/{base_slug}/{episode}/1080p.mp4"
        )

        qualities["HD"].append(
            f"{base}/mp4_temp/{base_slug}/{episode}/720p.mp4"
        )
        qualities["HD"].append(
            f"{base}/mp4/{base_slug}/hd/{episode}.mp4"
        )

        qualities["SD"].append(
            f"{base}/mp4_temp/{base_slug}/{episode}/480p.mp4"
        )
        qualities["SD"].append(
            f"{base}/mp4/{base_slug}/sd/{episode}.mp4"
        )

    return qualities


async def _find_first_valid_url(urls: list[str]) -> str:
    if not urls:
        return ""

    tasks = {asyncio.create_task(_check_candidate(url)): url for url in urls}

    try:
        for task in asyncio.as_completed(tasks):
            result = await task
            if result:
                for pending in tasks:
                    if pending is not task and not pending.done():
                        pending.cancel()
                return result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    return ""


async def _try_lightspeed_urls(base_slug: str, episode: str):
    quality_map = {}
    candidates = _build_candidate_urls(base_slug, episode)

    for quality in ("FULLHD", "HD", "SD"):
        found = await _find_first_valid_url(candidates.get(quality, []))
        if found:
            quality_map[quality] = found

    return quality_map


async def _try_blogger_or_googlevideo(base_slug: str, episode: str) -> str:
    try:
        episode_html = await _get_episode_page_html(base_slug, episode)

        direct_googlevideo = _extract_googlevideo_url(episode_html)
        if direct_googlevideo:
            return direct_googlevideo

        blogger_iframe = _extract_blogger_iframe(episode_html)
        if blogger_iframe:
            return blogger_iframe

    except Exception as e:
        print(f"[BLOGGER] erro_na_extracao={repr(e)}")

    return ""


async def _resolve_video_map(base_slug: str, episode: str, anime_id: str | None = None):
    cache_key = f"{base_slug}|{episode}"

    cached = _cache_get(_VIDEO_CACHE, cache_key, _VIDEO_CACHE_TTL)
    if cached is not None:
        return cached

    safe_base_slug = _normalize_episode_slug(base_slug)
    safe_anime_id = _normalize_episode_slug(anime_id or "")
    target_slug = safe_base_slug or safe_anime_id

    quality_map = await _try_lightspeed_urls(target_slug, episode)

    if not quality_map:
        alt_url = await _try_blogger_or_googlevideo(target_slug, episode)
        if alt_url:
            alt_quality = _normalize_quality_label(_extract_quality_name(alt_url)) or "HD"
            quality_map[alt_quality] = alt_url

    if not quality_map:
        fallback = f"https://lightspeedst.net/s6/mp4/{target_slug}/sd/{episode}.mp4"
        quality_map["SD"] = fallback

    _cache_set(_VIDEO_CACHE, cache_key, quality_map)
    return quality_map


async def get_episode_player(anime_id: str, episode: str, preferred_quality: str = "HD"):
    anime_id = _normalize_slug_for_page(anime_id)

    payload = await get_episodes(anime_id, 0, 3000)
    items = payload.get("items", [])

    base_slug = None
    index = None

    for i, item in enumerate(items):
        if str(item.get("episode")) == str(episode):
            base_slug = item.get("base_slug")
            index = i
            break

    if not base_slug:
        base_slug = anime_id.replace("-todos-os-episodios", "")

    quality_map = await _resolve_video_map(base_slug, episode, anime_id=anime_id)
    available_qualities = [q for q in ("FULLHD", "HD", "SD") if q in quality_map]

    preferred_quality = _normalize_quality_label(preferred_quality) or "HD"

    if preferred_quality in quality_map:
        selected_quality = preferred_quality
    elif preferred_quality == "FULLHD":
        if "HD" in quality_map:
            selected_quality = "HD"
        elif "SD" in quality_map:
            selected_quality = "SD"
        else:
            selected_quality = "FULLHD"
    elif preferred_quality == "HD":
        if "FULLHD" in quality_map:
            selected_quality = "FULLHD"
        elif "SD" in quality_map:
            selected_quality = "SD"
        else:
            selected_quality = "HD"
    else:
        if "HD" in quality_map:
            selected_quality = "HD"
        elif "FULLHD" in quality_map:
            selected_quality = "FULLHD"
        else:
            selected_quality = "SD"

    video = (quality_map.get(selected_quality) or "").strip()

    if not video:
        for fallback_quality in ("FULLHD", "HD", "SD"):
            fallback_video = (quality_map.get(fallback_quality) or "").strip()
            if fallback_video:
                selected_quality = fallback_quality
                video = fallback_video
                break

    server = _extract_server_name(video)
    quality = _extract_quality_name(video) if video else selected_quality

    prev_episode = None
    next_episode = None

    if index is not None:
        if index > 0:
            prev_episode = str(items[index - 1]["episode"])
        if index + 1 < len(items):
            next_episode = str(items[index + 1]["episode"])

    return {
        "video": video,
        "videos": quality_map,
        "base_slug": base_slug,
        "server": server,
        "quality": quality,
        "available_qualities": available_qualities,
        "prev_episode": prev_episode,
        "next_episode": next_episode,
        "total_episodes": len(items),
    }

import random
from urllib.parse import quote


GENRE_ALIASES = {
    "acao": ["acao", "ação", "action"],
    "romance": ["romance", "romantico", "romântico", "shoujo", "shojo"],
    "comedia": ["comedia", "comédia", "comedy"],
    "terror": ["terror", "horror", "sobrenatural"],
    "misterio": ["misterio", "mistério", "mystery", "suspense"],
    "fantasia": ["fantasia", "fantasy", "aventura"],
    "esportes": ["esporte", "esportes", "sports"],
    "drama": ["drama"],
}


def _extract_anime_links_from_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    links = soup.select("a[href*='/animes/']")

    for a in links:
        href = (a.get("href") or "").strip()
        if "/animes/" not in href:
            continue

        slug = href.split("/animes/")[-1].strip("/")
        if not slug or "/" in slug:
            continue

        title = _clean(a.get_text())
        if not title:
            img = a.find("img")
            if img:
                title = _clean(img.get("alt"))

        if not title:
            title = slug.replace("-", " ").title()

        found[slug] = {
            "id": slug,
            "title": title,
        }

    return list(found.values())


async def _get_genre_listing_candidates(genre_key: str) -> list[dict]:
    aliases = GENRE_ALIASES.get((genre_key or "").strip().lower(), [])
    if not aliases:
        return []

    items = {}

    for alias in aliases:
        alias = alias.strip().lower()

        possible_urls = [
            f"{BASE_URL}/genero/{quote(alias)}",
            f"{BASE_URL}/animes/genero/{quote(alias)}",
            f"{BASE_URL}/categoria/{quote(alias)}",
            f"{BASE_URL}/{quote(alias)}",
        ]

        for url in possible_urls:
            try:
                html = await _get(url)
                found = _extract_anime_links_from_listing(html)
                for item in found:
                    items[item["id"]] = item

                if len(items) >= 20:
                    return list(items.values())
            except Exception:
                continue

    return list(items.values())


async def get_random_anime_by_genre(genre_key: str, exclude_anime_id: str | None = None) -> dict:
    found = await _get_genre_listing_candidates(genre_key)

    if not found:
        raise RuntimeError(f"Nenhum anime encontrado para o gênero {genre_key}.")

    if exclude_anime_id:
        filtered = [item for item in found if item["id"] != exclude_anime_id]
        if filtered:
            found = filtered

    chosen = random.choice(found)
    return await get_anime_details(chosen["id"])