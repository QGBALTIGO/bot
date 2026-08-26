from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "personagens_anilist.txt"
OUTPUT_PATH = ROOT / "data" / "wallhaven_character_overrides.json"
STATE_PATH = ROOT / "data" / "wallhaven_curation_state.json"
API_SEARCH = "https://wallhaven.cc/api/v1/search"
API_WALLPAPER = "https://wallhaven.cc/api/v1/w/{wallpaper_id}"

TARGET_RATIO = 2.0 / 3.0
MIN_SOURCE_RATIO = 0.55
MAX_SOURCE_RATIO = 0.80
MIN_CROP_RETENTION = 0.82
MIN_WIDTH = 1000
MIN_HEIGHT = 1500
MIN_SCORE = 82.0
MAX_CANDIDATES = 4
REQUEST_DELAY = max(0.8, float(os.getenv("WALLHAVEN_CURATOR_DELAY", "1.45")))

SEARCH_ALIASES = {
    40: "Monkey D. Luffy",
    62: "Roronoa Zoro",
    61: "Nico Robin",
    305: "Sanji",
    2072: "Portgas D. Ace",
    16342: "Boa Hancock",
    727: "Shanks",
    13767: "Trafalgar Law",
    5: "Ichigo Kurosaki",
    6: "Rukia Kuchiki",
}

PRIORITY_CHARACTERS = (
    "luffy monkey", "zoro roronoa", "nami", "robin nico", "sanji", "sanji vinsmoke", "ace portgas",
    "hancock boa", "shanks", "law trafalgar", "naruto uzumaki", "sasuke uchiha", "sakura haruno",
    "kakashi hatake", "hinata hyuuga", "itachi uchiha", "gaara", "ichigo kurosaki", "rukia kuchiki",
    "orihime inoue", "byakuya kuchiki", "aizen sousuke", "goku son", "vegeta", "bulma",
    "gojo satoru", "itadori yuji", "fushiguro megumi", "kugisaki nobara", "sukuna ryomen",
    "maki zenin", "tanjiro kamado", "nezuko kamado", "zenitsu agatsuma", "inosuke hashibira",
    "shinobu kochou", "mitsuri kanroji", "rengoku kyoujurou", "giyuu tomioka", "frieren", "fern",
    "stark", "denji", "makima", "power", "aki hayakawa", "reze", "eren yeager", "mikasa ackerman",
    "levi", "armin arlert", "annie leonhart", "izuku midoriya", "katsuki bakugou", "shouto todoroki",
    "ochako uraraka", "gon freecss", "killua zoldyck", "kurapika", "hisoka morow", "edward elric",
    "alphonse elric", "roy mustang", "riza hawkeye", "light yagami", "lawliet", "misa amane",
    "anya forger", "yor forger", "loid forger", "ai hoshino", "aqua hoshino", "ruby hoshino",
    "kana arima", "sung jinwoo", "yoichi isagi", "meguru bachira", "seishirou nagi", "rin itoshi",
    "shouyou hinata", "tobio kageyama", "jotaro kujo", "dio brando", "giorno giovanna", "saitama",
    "genos", "ken kaneki", "touka kirishima", "lucy heartfilia", "erza scarlet", "natsu dragneel",
    "asta", "yuno", "noelle silva", "thorfinn", "askeladd", "kurisu makise", "rintarou okabe",
    "lelouch lamperouge", "cc", "rei ayanami", "asuka langley", "misato katsuragi", "spike spiegel",
    "faye valentine", "rem", "emilia", "ram", "megumin", "aqua", "darkness", "albedo",
    "ainz ooal gown", "kaguya shinomiya", "chika fujiwara", "hitori gotou", "momo ayase",
    "okarun", "kafka hibino", "mina ashiro", "pikachu", "ash ketchum", "saber",
)
PRIORITY_SERIES = (
    "one piece", "naruto", "bleach", "dragon ball", "jujutsu kaisen", "kimetsu no yaiba",
    "demon slayer", "sousou no frieren", "frieren", "chainsaw man", "shingeki no kyojin",
    "attack on titan", "boku no hero academia", "my hero academia", "hunter x hunter",
    "fullmetal alchemist", "death note", "spy x family", "oshi no ko", "solo leveling",
    "blue lock", "haikyuu", "jojo", "one punch man", "mob psycho", "tokyo ghoul",
    "fairy tail", "black clover", "vinland saga", "steins gate", "code geass",
    "neon genesis evangelion", "cowboy bebop", "re zero", "konosuba", "overlord",
    "kaguya sama", "bocchi the rock", "dandadan", "kaiju no 8", "pokemon",
)
GENERIC_CHARACTER_TAGS = {
    "anime girls", "anime girl", "anime boys", "anime boy", "manga girls", "manga girl",
    "original character", "original characters", "women", "woman", "men", "man",
}
GROUP_HINTS = {
    "two women", "two men", "two girls", "two boys", "2girls", "2boys",
    "group", "group of people", "couple", "duo", "multiple girls", "multiple boys",
}
STOP_TOKENS = {
    "the", "a", "an", "of", "and", "no", "to", "in", "on", "season", "part",
    "tv", "movie", "ova", "special", "ii", "iii", "iv", "2nd", "3rd", "final",
}


class RateLimitError(RuntimeError):
    def __init__(self, retry_after: float = 60.0):
        super().__init__("Wallhaven rate limit reached")
        self.retry_after = max(5.0, min(float(retry_after or 60.0), 120.0))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def tokens(value: Any) -> set[str]:
    return {x for x in norm(value).split() if len(x) >= 2 and x not in STOP_TOKENS}


def crop_retention_for_ratio(ratio: float) -> float:
    value = float(ratio or 0.0)
    if value <= 0:
        return 0.0
    if value >= TARGET_RATIO:
        return TARGET_RATIO / value
    return value / TARGET_RATIO


def variants(name: Any, alias: Any = "") -> list[str]:
    raw = [str(name or "")]
    raw.extend(re.split(r"[,;/|]", str(alias or "")))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        n = norm(item)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def similarity(target: str, candidate: str) -> float:
    a = tokens(target)
    b = tokens(candidate)
    if not a or not b:
        return 0.0
    if norm(target) == norm(candidate):
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    jaccard = inter / union if union else 0.0
    containment = inter / len(a) if a else 0.0
    reverse_containment = inter / len(b) if b else 0.0
    return max(jaccard, containment * 0.96, reverse_containment * 0.88)


def tag_best_match(target: str, tag: dict[str, Any]) -> float:
    return max((similarity(target, item) for item in variants(tag.get("name"), tag.get("alias"))), default=0.0)


def specific_character_tags(tags: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for tag in tags:
        if str(tag.get("category") or "").casefold() != "characters":
            continue
        name = norm(tag.get("name"))
        if not name or name in GENERIC_CHARACTER_TAGS:
            continue
        out.append(tag)
    return out


def evaluate_candidate(detail: dict[str, Any], character_name: str, anime_title: str) -> dict[str, Any] | None:
    if str(detail.get("purity") or "").casefold() != "sfw":
        return None
    if str(detail.get("category") or "").casefold() != "anime":
        return None

    width = int(detail.get("dimension_x") or 0)
    height = int(detail.get("dimension_y") or 0)
    if width < MIN_WIDTH or height < MIN_HEIGHT or width >= height:
        return None

    ratio = width / height if height else 0.0
    crop_retention = crop_retention_for_ratio(ratio)
    if not (MIN_SOURCE_RATIO <= ratio <= MAX_SOURCE_RATIO):
        return None
    if crop_retention < MIN_CROP_RETENTION:
        return None

    tags = [x for x in (detail.get("tags") or []) if isinstance(x, dict)]
    all_tag_variants = {
        variant
        for tag in tags
        for variant in variants(tag.get("name"), tag.get("alias"))
    }
    if any(hint in all_tag_variants for hint in GROUP_HINTS):
        return None

    char_tags = specific_character_tags(tags)
    series_tags = [x for x in tags if str(x.get("category") or "").casefold() == "series"]

    char_match = max((tag_best_match(character_name, x) for x in char_tags), default=0.0)
    series_match = max((tag_best_match(anime_title, x) for x in series_tags), default=0.0)
    if char_match < 0.76 or series_match < 0.58:
        return None

    other_specific = [x for x in char_tags if tag_best_match(character_name, x) < 0.76]
    # Character portraits must be solo. Any second specific character tag
    # rejects the wallpaper, even when the target character is correct.
    if other_specific:
        return None

    ratio_score = crop_retention * 32.0
    identity_score = char_match * 31.0 + series_match * 17.0
    pixels = width * height
    resolution_score = min(11.0, math.log1p(max(1.0, pixels / 1_000_000.0)) * 6.0)
    favorites = max(0, int(detail.get("favorites") or 0))
    views = max(0, int(detail.get("views") or 0))
    popularity_score = min(5.0, math.log1p(favorites) * 1.05) + min(3.0, math.log1p(views) * 0.32)
    solo_bonus = 8.0
    type_bonus = 1.5 if str(detail.get("file_type") or "").casefold() in {"image/jpeg", "image/png", "image/webp"} else 0.0

    score = round(ratio_score + identity_score + resolution_score + popularity_score + solo_bonus + type_bonus, 3)
    if score < MIN_SCORE:
        return None

    path = str(detail.get("path") or "").strip()
    if not path.startswith("https://"):
        return None

    return {
        "url": path,
        "wallhaven_id": str(detail.get("id") or ""),
        "width": width,
        "height": height,
        "ratio": round(ratio, 5),
        "crop_2x3": True,
        "crop_retention": round(crop_retention, 5),
        "score": score,
        "favorites": favorites,
        "views": views,
        "character_match": round(char_match, 4),
        "series_match": round(series_match, 4),
        "character_tags": [str(x.get("name") or "") for x in char_tags],
        "series_tags": [str(x.get("name") or "") for x in series_tags],
        "other_characters": [str(x.get("name") or "") for x in other_specific],
        "source_page": str(detail.get("url") or ""),
    }


def character_priority(name: str) -> int:
    name_norm = norm(name)
    name_tokens = tokens(name)
    for index, target in enumerate(PRIORITY_CHARACTERS):
        if name_norm == norm(target) or (name_tokens and name_tokens == tokens(target)):
            return index
    return len(PRIORITY_CHARACTERS) + 1


def series_priority(title: str) -> int:
    n = norm(title)
    for index, pattern in enumerate(PRIORITY_SERIES):
        if pattern in n:
            return index
    return len(PRIORITY_SERIES) + 1


def load_characters() -> list[dict[str, Any]]:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    animes = raw.get("items", []) if isinstance(raw, dict) else raw
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for anime in animes or []:
        if not isinstance(anime, dict):
            continue
        anime_title = str(anime.get("anime") or "").strip()
        anime_id = int(anime.get("anime_id") or 0)
        for character in anime.get("characters", []) or []:
            if not isinstance(character, dict):
                continue
            cid = int(character.get("id") or 0)
            name = str(character.get("name") or "").strip()
            if cid <= 0 or not name or cid in seen:
                continue
            seen.add(cid)
            out.append({
                "id": cid,
                "name": name,
                "anime": anime_title,
                "anime_id": anime_id,
                "anilist_url": str(character.get("image") or "").strip(),
            })
    out.sort(
        key=lambda x: (
            character_priority(x["name"]),
            series_priority(x["anime"]),
            norm(x["anime"]),
            norm(x["name"]),
            x["id"],
        )
    )
    return out


def load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return raw if isinstance(raw, dict) else fallback


def load_output() -> dict[str, Any]:
    raw = load_json(OUTPUT_PATH, {"version": 1, "source": "wallhaven", "characters": {}})
    raw.setdefault("version", 1)
    raw.setdefault("source", "wallhaven")
    if not isinstance(raw.get("characters"), dict):
        raw["characters"] = {}
    return raw


def load_state() -> dict[str, Any]:
    raw = load_json(STATE_PATH, {"version": 1, "processed": {}})
    raw.setdefault("version", 1)
    if not isinstance(raw.get("processed"), dict):
        raw["processed"] = {}
    return raw


def retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 60.0


def _search_shape_ok(item: dict[str, Any]) -> bool:
    width = int(item.get("dimension_x") or 0)
    height = int(item.get("dimension_y") or 0)
    if width < MIN_WIDTH or height < MIN_HEIGHT or width >= height:
        return False
    ratio = width / height if height else 0.0
    return (
        MIN_SOURCE_RATIO <= ratio <= MAX_SOURCE_RATIO
        and crop_retention_for_ratio(ratio) >= MIN_CROP_RETENTION
    )


def search_candidates(client: httpx.Client, query: str, api_key: str) -> list[dict[str, Any]]:
    # Do not use Wallhaven's ratios=2x3 bucket. It excludes many excellent
    # near-2:3 portraits (e.g. 1488x2256). Fetch high-resolution results and
    # apply our own numeric ratio rule before spending requests on details.
    params = {
        "q": query,
        "categories": "010",
        "purity": "100",
        "sorting": "relevance",
        "order": "desc",
        "atleast": f"{MIN_WIDTH}x{MIN_HEIGHT}",
        "page": "1",
    }
    if api_key:
        params["apikey"] = api_key
    response = client.get(API_SEARCH, params=params)
    if response.status_code == 429:
        raise RateLimitError(retry_after(response))
    response.raise_for_status()
    payload = response.json()
    items = [x for x in ((payload or {}).get("data") or []) if isinstance(x, dict)]
    return [x for x in items if _search_shape_ok(x)]


def fetch_detail(client: httpx.Client, wallpaper_id: str, api_key: str) -> dict[str, Any]:
    params = {"apikey": api_key} if api_key else None
    response = client.get(API_WALLPAPER.format(wallpaper_id=wallpaper_id), params=params)
    if response.status_code == 429:
        raise RateLimitError(retry_after(response))
    response.raise_for_status()
    payload = response.json()
    return (payload or {}).get("data") or {}


def curate_one(client: httpx.Client, character: dict[str, Any], api_key: str) -> tuple[dict[str, Any] | None, str]:
    # Search by a canonical alias when AniList stores the name in a form
    # Wallhaven rarely indexes. Series identity is still mandatory in tags.
    query = SEARCH_ALIASES.get(int(character["id"]), character["name"])
    candidates = search_candidates(client, query, api_key)
    time.sleep(REQUEST_DELAY)
    if not candidates:
        return None, "no_search_result"

    evaluated: list[dict[str, Any]] = []
    for item in candidates[:MAX_CANDIDATES]:
        wid = str(item.get("id") or "")
        if not wid:
            continue
        detail = fetch_detail(client, wid, api_key)
        time.sleep(REQUEST_DELAY)
        scored = evaluate_candidate(detail, character["name"], character["anime"])
        if scored:
            scored["query"] = query
            evaluated.append(scored)

    if not evaluated:
        return None, "no_strict_match"
    evaluated.sort(key=lambda x: (float(x["score"]), int(x["favorites"]), int(x["views"])), reverse=True)
    return evaluated[0], "approved"


def write_state(output: dict[str, Any], state: dict[str, Any]) -> None:
    output["generated_at"] = now_iso()
    output["filters"] = {
        "purity": "sfw",
        "category": "anime",
        "output_ratio": "2:3 exact via image proxy crop",
        "source_ratio_min": MIN_SOURCE_RATIO,
        "source_ratio_max": MAX_SOURCE_RATIO,
        "min_crop_retention": MIN_CROP_RETENTION,
        "min_width": MIN_WIDTH,
        "min_height": MIN_HEIGHT,
        "min_score": MIN_SCORE,
        "character_tag_required": True,
        "series_tag_required": True,
        "max_other_specific_characters": 0,
    }
    state["updated_at"] = now_iso()
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate strict 2:3 Wallhaven portraits for Baltigo characters")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--retry-existing", action="store_true")
    parser.add_argument("--retry-misses", action="store_true")
    parser.add_argument("--contains", default="", help="Only process character/anime rows containing this text")
    args = parser.parse_args()

    characters = load_characters()
    if args.contains:
        needle = norm(args.contains)
        characters = [x for x in characters if needle in norm(f"{x['name']} {x['anime']}")]

    output = load_output()
    state = load_state()
    existing = output["characters"]
    processed = state["processed"]
    start = max(0, args.offset)
    batch = characters[start: start + max(1, args.limit)]
    api_key = os.getenv("WALLHAVEN_API_KEY", "").strip()
    headers = {"User-Agent": "SourceBaltigo-Wallhaven-Curator/2.1"}
    stats = {
        "approved": 0,
        "no_search_result": 0,
        "no_strict_match": 0,
        "skipped_existing": 0,
        "skipped_processed": 0,
        "errors": 0,
        "rate_waits": 0,
    }

    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        for index, character in enumerate(batch, start=start):
            cid_key = str(character["id"])
            previous = processed.get(cid_key) if isinstance(processed.get(cid_key), dict) else {}
            previous_status = str((previous or {}).get("status") or "")

            if cid_key in existing and not args.retry_existing:
                stats["skipped_existing"] += 1
                continue
            if previous_status and previous_status != "approved" and not args.retry_misses:
                stats["skipped_processed"] += 1
                continue

            selected = None
            status = "error"
            for attempt in range(3):
                try:
                    selected, status = curate_one(client, character, api_key)
                    break
                except RateLimitError as exc:
                    stats["rate_waits"] += 1
                    print(f"RATE_WAIT index={index} seconds={exc.retry_after:.1f}", flush=True)
                    time.sleep(exc.retry_after)
                except httpx.HTTPError:
                    if attempt >= 2:
                        raise
                    time.sleep(3.0 * (attempt + 1))

            if status == "error" and selected is None:
                stats["errors"] += 1
                continue

            stats[status] = stats.get(status, 0) + 1
            processed[cid_key] = {
                "status": status,
                "character_name": character["name"],
                "anime": character["anime"],
                "checked_at": now_iso(),
            }

            if selected:
                record = {
                    "character_id": character["id"],
                    "character_name": character["name"],
                    "anime_id": character["anime_id"],
                    "anime": character["anime"],
                    "anilist_fallback": character["anilist_url"],
                    **selected,
                    "approved_at": now_iso(),
                }
                print(
                    f"APPROVE index={index} id={cid_key} {character['name']} / {character['anime']} "
                    f"score={record['score']} {record['width']}x{record['height']} wh={record['wallhaven_id']} "
                    f"others={record['other_characters']}",
                    flush=True,
                )
                if args.apply:
                    existing[cid_key] = record
            else:
                print(f"MISS index={index} id={cid_key} {character['name']} / {character['anime']} status={status}", flush=True)

            if args.apply:
                write_state(output, state)

    if args.apply:
        write_state(output, state)

    print(
        "SUMMARY",
        json.dumps(
            {
                **stats,
                "batch": len(batch),
                "total_characters": len(characters),
                "stored": len(existing),
                "processed": len(processed),
                "api_key": bool(api_key),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
