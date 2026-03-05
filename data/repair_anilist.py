import os
import re
import json
import time
import asyncio
import aiohttp
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

FILES = [
    "data/catalogo_enriquecido.json",
    "data/catalogo_mangas_enriquecido.json",
]

ANILIST_URL = "https://graphql.anilist.co"
KITSU_ANIME_SEARCH = "https://kitsu.io/api/edge/anime"
KITSU_MANGA_SEARCH = "https://kitsu.io/api/edge/manga"
JIKAN_ANIME_SEARCH = "https://api.jikan.moe/v4/anime"
JIKAN_MANGA_SEARCH = "https://api.jikan.moe/v4/manga"

# Ajuste se quiser (quanto mais alto, mais rápido, mas mais chance de rate-limit)
CONCURRENCY = int(os.getenv("COVER_FIX_CONCURRENCY", "6"))

# Quantas tentativas em caso de 429/timeout
RETRIES = int(os.getenv("COVER_FIX_RETRIES", "3"))

# Pausa pequena entre requisições (ajuda a não tomar ban)
BASE_SLEEP = float(os.getenv("COVER_FIX_SLEEP", "0.12"))

UA = os.getenv("COVER_FIX_UA", "SourceBaltigoCatalogBot/1.0")


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _strip(s: Any) -> str:
    return str(s or "").strip()


def _normalize_title(s: str) -> str:
    s = _strip(s)
    s = re.sub(r"\s+", " ", s)
    # remove “| BLEACH”, “- 1080p”, etc (leve)
    s = re.sub(r"\s*\|\s*.*$", "", s).strip()
    s = re.sub(r"\s*-\s*\d+p\s*$", "", s, flags=re.I).strip()
    return s


def _guess_kind(rec: Dict[str, Any]) -> str:
    """
    Retorna: "anime" | "manga"
    """
    raw = (_strip(rec.get("raw_text")) + " " + _strip(rec.get("title_raw"))).lower()
    # pistas fortes de manga/manhwa/manhua
    if "formato: mang" in raw or "manhwa" in raw or "manhua" in raw or "mangá" in raw or "manga" in raw:
        return "manga"
    # se veio do arquivo de mangas
    post = _strip(rec.get("post_url")).lower()
    if "t.me/mangasbrasil" in post:
        return "manga"
    return "anime"


def _best_title_candidate(rec: Dict[str, Any]) -> str:
    title = _normalize_title(
        _strip(rec.get("title_raw")) or _strip(rec.get("titulo")) or _strip(rec.get("title"))
    )
    if not title:
        raw_text = _strip(rec.get("raw_text"))
        if raw_text:
            title = _normalize_title(raw_text.splitlines()[0])
    return title


def _pick_year_from_date(s: str) -> Optional[int]:
    s = _strip(s)
    if not s:
        return None
    m = re.match(r"^(\d{4})", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except:
        return None


def _cover_from_anilist(media: Dict[str, Any]) -> str:
    cover = media.get("coverImage") or {}
    # prefira extraLarge/large
    return _strip(cover.get("extraLarge") or cover.get("large") or cover.get("medium"))


def _title_from_anilist(media: Dict[str, Any]) -> str:
    t = media.get("title") or {}
    return _strip(t.get("romaji") or t.get("english") or t.get("native"))


def _format_from_anilist(media: Dict[str, Any], kind: str) -> str:
    # AniList usa formatos: TV, MOVIE, OVA, ONA, SPECIAL, MANGA, NOVEL, ONE_SHOT...
    fmt = _strip(media.get("format"))
    if fmt:
        return fmt
    return "MANGA" if kind == "manga" else "TV"


def _score_from_anilist(media: Dict[str, Any]) -> Optional[int]:
    v = media.get("averageScore")
    try:
        if v is None:
            return None
        return int(v)
    except:
        return None


def _year_from_anilist(media: Dict[str, Any]) -> Optional[int]:
    y = media.get("seasonYear")
    try:
        if y is None:
            return None
        return int(y)
    except:
        return None


def _cover_from_kitsu(item: Dict[str, Any]) -> str:
    attrs = item.get("attributes") or {}
    ci = attrs.get("posterImage") or {}
    return _strip(ci.get("original") or ci.get("large") or ci.get("medium") or ci.get("small"))


def _title_from_kitsu(item: Dict[str, Any]) -> str:
    attrs = item.get("attributes") or {}
    return _strip(attrs.get("canonicalTitle") or attrs.get("titles", {}).get("en") or attrs.get("slug"))


def _score_from_kitsu(item: Dict[str, Any]) -> Optional[int]:
    attrs = item.get("attributes") or {}
    # averageRating pode vir "85.23" (0-100) como string
    ar = attrs.get("averageRating")
    if ar is None:
        return None
    try:
        f = float(str(ar))
        # geralmente já é 0..100
        if f <= 10.5:
            f = f * 10.0
        return int(round(f))
    except:
        return None


def _year_from_kitsu(item: Dict[str, Any]) -> Optional[int]:
    attrs = item.get("attributes") or {}
    start = _strip(attrs.get("startDate"))
    return _pick_year_from_date(start)


def _format_from_kitsu(kind: str) -> str:
    # kitsu não tem o mesmo "format" do AniList facilmente; define básico
    return "MANGA" if kind == "manga" else "TV"


def _cover_from_jikan(item: Dict[str, Any]) -> str:
    img = item.get("images") or {}
    jpg = img.get("jpg") or {}
    webp = img.get("webp") or {}
    return _strip(jpg.get("large_image_url") or jpg.get("image_url") or webp.get("large_image_url") or webp.get("image_url"))


def _title_from_jikan(item: Dict[str, Any]) -> str:
    return _strip(item.get("title") or item.get("title_english") or item.get("title_japanese"))


def _score_from_jikan(item: Dict[str, Any]) -> Optional[int]:
    # score 0..10
    v = item.get("score")
    try:
        if v is None:
            return None
        f = float(v)
        return int(round(f * 10.0))
    except:
        return None


def _year_from_jikan(item: Dict[str, Any]) -> Optional[int]:
    y = item.get("year")
    try:
        if y is None:
            # fallback: aired/from, published/from
            aired = item.get("aired") or {}
            published = item.get("published") or {}
            from_ = _strip(aired.get("from") or published.get("from"))
            return _pick_year_from_date(from_)
        return int(y)
    except:
        return None


def _format_from_jikan(item: Dict[str, Any], kind: str) -> str:
    # anime: type = TV/Movie/OVA/ONA...
    # manga: type = Manga/Manhwa/Manhua/Novel/One-shot...
    t = _strip(item.get("type"))
    if not t:
        return "MANGA" if kind == "manga" else "TV"
    return t.upper() if kind == "anime" else t.upper()


async def _fetch_json(session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> Any:
    for attempt in range(RETRIES):
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status == 429:
                    wait = 1.2 + attempt * 1.3
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return await resp.json()
        except Exception:
            if attempt == RETRIES - 1:
                raise
            await asyncio.sleep(0.6 + attempt * 0.7)
    raise RuntimeError("unreachable")


async def _search_anilist(session: aiohttp.ClientSession, title: str, kind: str) -> Optional[Dict[str, Any]]:
    # kind: anime/manga
    query = """
    query ($search: String) {
      Media(search: $search, type: __TYPE__) {
        id
        title { romaji english native }
        format
        averageScore
        seasonYear
        coverImage { extraLarge large medium }
      }
    }
    """.replace("__TYPE__", "MANGA" if kind == "manga" else "ANIME")

    payload = {"query": query, "variables": {"search": title}}
    try:
        data = await _fetch_json(
            session,
            "POST",
            ANILIST_URL,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        media = (((data or {}).get("data") or {}).get("Media")) or None
        if not isinstance(media, dict):
            return None

        cover = _cover_from_anilist(media)
        tdisp = _title_from_anilist(media) or title
        fmt = _format_from_anilist(media, kind)
        score = _score_from_anilist(media)
        year = _year_from_anilist(media)

        # precisa ter cover pra valer
        if not cover:
            return None

        return {
            "provider": "anilist",
            "title_display": tdisp,
            "cover": cover,
            "format": fmt,
            "averageScore": score,
            "seasonYear": year,
        }
    except Exception:
        return None


async def _search_kitsu(session: aiohttp.ClientSession, title: str, kind: str) -> Optional[Dict[str, Any]]:
    url = KITSU_MANGA_SEARCH if kind == "manga" else KITSU_ANIME_SEARCH
    params = {"filter[text]": title, "page[limit]": "1"}
    try:
        data = await _fetch_json(
            session,
            "GET",
            url,
            params=params,
            headers={"User-Agent": UA},
        )
        items = (data or {}).get("data") or []
        if not items or not isinstance(items, list):
            return None
        it = items[0]
        if not isinstance(it, dict):
            return None

        cover = _cover_from_kitsu(it)
        if not cover:
            return None

        tdisp = _title_from_kitsu(it) or title
        score = _score_from_kitsu(it)
        year = _year_from_kitsu(it)
        fmt = _format_from_kitsu(kind)

        return {
            "provider": "kitsu",
            "title_display": tdisp,
            "cover": cover,
            "format": fmt,
            "averageScore": score,
            "seasonYear": year,
        }
    except Exception:
        return None


async def _search_jikan(session: aiohttp.ClientSession, title: str, kind: str) -> Optional[Dict[str, Any]]:
    url = JIKAN_MANGA_SEARCH if kind == "manga" else JIKAN_ANIME_SEARCH
    params = {"q": title, "limit": "1"}
    try:
        data = await _fetch_json(
            session,
            "GET",
            url,
            params=params,
            headers={"User-Agent": UA},
        )
        items = (data or {}).get("data") or []
        if not items or not isinstance(items, list):
            return None
        it = items[0]
        if not isinstance(it, dict):
            return None

        cover = _cover_from_jikan(it)
        if not cover:
            return None

        tdisp = _title_from_jikan(it) or title
        score = _score_from_jikan(it)
        year = _year_from_jikan(it)
        fmt = _format_from_jikan(it, kind)

        return {
            "provider": "jikan",
            "title_display": tdisp,
            "cover": cover,
            "format": fmt,
            "averageScore": score,
            "seasonYear": year,
        }
    except Exception:
        return None


async def _enrich_one(session: aiohttp.ClientSession, rec: Dict[str, Any], sem: asyncio.Semaphore) -> Tuple[bool, str]:
    title = _best_title_candidate(rec)
    if not title:
        return False, "sem titulo"

    kind = _guess_kind(rec)

    # se já tem cover válido, não mexe (pra não gastar API)
    an = rec.get("anilist")
    if isinstance(an, dict) and _strip(an.get("cover")):
        return False, "já tem cover"

    async with sem:
        await asyncio.sleep(BASE_SLEEP)

        # 1) AniList
        r = await _search_anilist(session, title, kind)
        if r:
            rec["anilist"] = r
            return True, f"OK anilist ({kind})"

        # 2) Kitsu
        r = await _search_kitsu(session, title, kind)
        if r:
            rec["anilist"] = r  # mantém chave "anilist" por compatibilidade do webapp
            return True, f"OK kitsu ({kind})"

        # 3) Jikan
        r = await _search_jikan(session, title, kind)
        if r:
            rec["anilist"] = r
            return True, f"OK jikan ({kind})"

        return False, f"NO match ({kind})"


async def _process_file(path: str) -> None:
    if not os.path.exists(path):
        print(f"[skip] não achei: {path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records")
    if not isinstance(records, list):
        raise RuntimeError(f"{path}: JSON não tem records[]")

    sem = asyncio.Semaphore(CONCURRENCY)

    timeout = aiohttp.ClientTimeout(total=25)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2, ttl_dns_cache=300)

    changed = 0
    ok_anilist = 0
    ok_kitsu = 0
    ok_jikan = 0
    no_match = 0

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            tasks.append(_enrich_one(session, rec, sem))

        results = []
        # processa em lotes pra log ficar legível
        CHUNK = 60
        for i in range(0, len(tasks), CHUNK):
            chunk = tasks[i : i + CHUNK]
            chunk_res = await asyncio.gather(*chunk, return_exceptions=True)
            results.extend(chunk_res)

    # contabiliza
    idx = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        r = results[idx]
        idx += 1
        if isinstance(r, Exception):
            no_match += 1
            continue
        did, msg = r
        if did:
            changed += 1
            prov = (rec.get("anilist") or {}).get("provider")
            if prov == "anilist":
                ok_anilist += 1
            elif prov == "kitsu":
                ok_kitsu += 1
            elif prov == "jikan":
                ok_jikan += 1
        else:
            if msg.startswith("NO match"):
                no_match += 1

    data["generated_at"] = _now_iso()
    data["cover_enrichment"] = {
        "strategy": "anilist->kitsu->jikan",
        "changed": changed,
        "ok_anilist": ok_anilist,
        "ok_kitsu": ok_kitsu,
        "ok_jikan": ok_jikan,
        "no_match": no_match,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(
        f"[done] {path} | changed={changed} anilist={ok_anilist} kitsu={ok_kitsu} jikan={ok_jikan} no_match={no_match}"
    )


async def main():
    print("[start] cover enrichment:", FILES)
    t0 = time.time()
    for p in FILES:
        await _process_file(p)
    print("[end] secs:", round(time.time() - t0, 2))


if __name__ == "__main__":
    asyncio.run(main())
