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
API_SEARCH = "https://wallhaven.cc/api/v1/search"
API_WALLPAPER = "https://wallhaven.cc/api/v1/w/{wallpaper_id}"

TARGET_RATIO = 2.0 / 3.0
RATIO_TOLERANCE = 0.035
MIN_WIDTH = 1000
MIN_HEIGHT = 1500
MIN_SCORE = 82.0
MAX_CANDIDATES = 5
REQUEST_DELAY = 0.22
GENERIC_CHARACTER_TAGS = {
    "anime girls", "anime girl", "anime boys", "anime boy", "manga girls", "manga girl",
    "original character", "original characters", "women", "woman", "men", "man",
}
STOP_TOKENS = {
    "the", "a", "an", "of", "and", "no", "to", "in", "on", "season", "part",
    "tv", "movie", "ova", "special", "ii", "iii", "iv", "2nd", "3rd", "final",
}


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def tokens(value: Any) -> set[str]:
    return {x for x in norm(value).split() if len(x) >= 2 and x not in STOP_TOKENS}


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
    return max(jaccard, containment * 0.96)


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
    ratio_distance = abs(ratio - TARGET_RATIO)
    if ratio_distance > RATIO_TOLERANCE:
        return None

    tags = [x for x in (detail.get("tags") or []) if isinstance(x, dict)]
    char_tags = specific_character_tags(tags)
    series_tags = [x for x in tags if str(x.get("category") or "").casefold() == "series"]

    char_match = max((tag_best_match(character_name, x) for x in char_tags), default=0.0)
    series_match = max((tag_best_match(anime_title, x) for x in series_tags), default=0.0)

    # Identity is mandatory. Weak textual matches are not allowed to replace AniList.
    if char_match < 0.76 or series_match < 0.58:
        return None

    other_specific = [x for x in char_tags if tag_best_match(character_name, x) < 0.76]
    if len(other_specific) >= 3:
        return None

    ratio_score = max(0.0, 1.0 - ratio_distance / RATIO_TOLERANCE) * 32.0
    identity_score = char_match * 31.0 + series_match * 17.0
    pixels = width * height
    resolution_score = min(11.0, math.log1p(max(1, pixels / 1_000_000.0)) * 6.0)
    favorites = max(0, int(detail.get("favorites") or 0))
    views = max(0, int(detail.get("views") or 0))
    popularity_score = min(5.0, math.log1p(favorites) * 1.05) + min(3.0, math.log1p(views) * 0.32)
    solo_bonus = 8.0 if not other_specific else max(0.0, 5.0 - 2.5 * len(other_specific))
    jpeg_bonus = 1.5 if str(detail.get("file_type") or "").casefold() in {"image/jpeg", "image/png", "image/webp"} else 0.0

    score = round(ratio_score + identity_score + resolution_score + popularity_score + solo_bonus + jpeg_bonus, 3)
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
    out.sort(key=lambda x: (norm(x["anime"]), norm(x["name"]), x["id"]))
    return out


def load_output() -> dict[str, Any]:
    if not OUTPUT_PATH.exists():
        return {"version": 1, "source": "wallhaven", "characters": {}}
    try:
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("version", 1)
    raw.setdefault("source", "wallhaven")
    if not isinstance(raw.get("characters"), dict):
        raw["characters"] = {}
    return raw


def search_candidates(client: httpx.Client, query: str, api_key: str) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "categories": "010",
        "purity": "100",
        "sorting": "relevance",
        "order": "desc",
        "atleast": f"{MIN_WIDTH}x{MIN_HEIGHT}",
        "ratios": "2x3",
        "page": "1",
    }
    if api_key:
        params["apikey"] = api_key
    response = client.get(API_SEARCH, params=params)
    if response.status_code == 429:
        raise RuntimeError("Wallhaven rate limit reached")
    response.raise_for_status()
    payload = response.json()
    return [x for x in ((payload or {}).get("data") or []) if isinstance(x, dict)]


def fetch_detail(client: httpx.Client, wallpaper_id: str, api_key: str) -> dict[str, Any]:
    params = {"apikey": api_key} if api_key else None
    response = client.get(API_WALLPAPER.format(wallpaper_id=wallpaper_id), params=params)
    if response.status_code == 429:
        raise RuntimeError("Wallhaven rate limit reached")
    response.raise_for_status()
    payload = response.json()
    return (payload or {}).get("data") or {}


def curate_one(client: httpx.Client, character: dict[str, Any], api_key: str) -> tuple[dict[str, Any] | None, str]:
    queries = [
        f'"{character["name"]}" "{character["anime"]}"',
        f'{character["name"]} {character["anime"]}',
        character["name"],
    ]
    seen_ids: set[str] = set()
    evaluated: list[dict[str, Any]] = []

    for query in queries:
        try:
            candidates = search_candidates(client, query, api_key)
        except httpx.HTTPError:
            continue
        for item in candidates[:MAX_CANDIDATES]:
            wid = str(item.get("id") or "")
            if not wid or wid in seen_ids:
                continue
            seen_ids.add(wid)
            time.sleep(REQUEST_DELAY)
            try:
                detail = fetch_detail(client, wid, api_key)
            except httpx.HTTPError:
                continue
            scored = evaluate_candidate(detail, character["name"], character["anime"])
            if scored:
                scored["query"] = query
                evaluated.append(scored)
        if evaluated:
            # Exact character+series searches should win over looser fallbacks.
            break
        time.sleep(REQUEST_DELAY)

    if not evaluated:
        return None, "no_strict_match"
    evaluated.sort(key=lambda x: (float(x["score"]), int(x["favorites"]), int(x["views"])), reverse=True)
    return evaluated[0], "approved"


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate strict 2:3 Wallhaven portraits for Baltigo characters")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--retry-existing", action="store_true")
    args = parser.parse_args()

    characters = load_characters()
    output = load_output()
    existing = output["characters"]
    batch = characters[max(0, args.offset): max(0, args.offset) + max(1, args.limit)]
    api_key = os.getenv("WALLHAVEN_API_KEY", "").strip()

    headers = {"User-Agent": "SourceBaltigo-Wallhaven-Curator/1.0"}
    stats = {"approved": 0, "no_strict_match": 0, "skipped_existing": 0, "errors": 0}

    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        for index, character in enumerate(batch, start=args.offset):
            cid_key = str(character["id"])
            if cid_key in existing and not args.retry_existing:
                stats["skipped_existing"] += 1
                print(f"SKIP index={index} id={cid_key} {character['name']} / {character['anime']} existing")
                continue

            try:
                selected, status = curate_one(client, character, api_key)
            except RuntimeError as exc:
                print(f"STOP index={index} reason={exc}")
                break
            except Exception as exc:
                stats["errors"] += 1
                print(f"ERROR index={index} id={cid_key} {type(exc).__name__}: {exc}")
                continue

            stats[status] = stats.get(status, 0) + 1
            if not selected:
                print(f"MISS index={index} id={cid_key} {character['name']} / {character['anime']}")
                continue

            record = {
                "character_id": character["id"],
                "character_name": character["name"],
                "anime_id": character["anime_id"],
                "anime": character["anime"],
                "anilist_fallback": character["anilist_url"],
                **selected,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
            print(
                f"APPROVE index={index} id={cid_key} {character['name']} / {character['anime']} "
                f"score={record['score']} {record['width']}x{record['height']} wh={record['wallhaven_id']} "
                f"others={record['other_characters']}"
            )
            if args.apply:
                existing[cid_key] = record

            time.sleep(REQUEST_DELAY)

    if args.apply:
        output["generated_at"] = datetime.now(timezone.utc).isoformat()
        output["filters"] = {
            "purity": "sfw",
            "category": "anime",
            "ratio": "2:3",
            "ratio_tolerance": RATIO_TOLERANCE,
            "min_width": MIN_WIDTH,
            "min_height": MIN_HEIGHT,
            "min_score": MIN_SCORE,
            "character_tag_required": True,
            "series_tag_required": True,
            "max_other_specific_characters": 2,
        }
        OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("SUMMARY", json.dumps({**stats, "batch": len(batch), "total_characters": len(characters), "stored": len(existing)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
