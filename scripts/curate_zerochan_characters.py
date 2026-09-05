from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "personagens_anilist.txt"
WALLHAVEN_PATH = ROOT / "data" / "wallhaven_character_overrides.json"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "zerochan_test_results.json"
ZEROCHAN_BASE_URL = "https://www.zerochan.net"

DEFAULT_TEST_IDS = (40, 62, 723, 137080, 137079, 176754, 183965, 130102, 127518, 133700)

ZEROCHAN_TAG_ALIASES = {
    40: "Monkey D. Luffy",
    62: "Roronoa Zoro",
    723: "Nami (ONE PIECE)",
    61: "Nico Robin",
    305: "Sanji",
    2072: "Portgas D. Ace",
    16342: "Boa Hancock",
    13767: "Trafalgar Law",
    5: "Kurosaki Ichigo",
    6: "Kuchiki Rukia",
    176754: "Frieren",
    183965: "Fern",
    137080: "Makima",
    137079: "Power (Chainsaw Man)",
}

SERIES_ALIASES = {
    "one piece": ("one piece",),
    "chainsaw man": ("chainsaw man",),
    "sousou no frieren": ("sousou no frieren", "frieren beyond journeys end"),
    "kimetsu no yaiba": ("kimetsu no yaiba", "demon slayer"),
    "boku no hero academia": ("boku no hero academia", "my hero academia"),
    "shingeki no kyojin": ("shingeki no kyojin", "attack on titan"),
    "hunter hunter": ("hunter hunter", "hunter x hunter"),
}

HARD_REJECT_TAGS = {
    "cosplay", "screenshot", "fake screenshot", "character request", "artist request",
    "no character", "no people", "duo", "trio", "quartet", "quintet", "group",
    "large group", "two girls", "two males", "two boys", "three girls", "three males",
    "four girls", "four males", "five girls", "five males",
}
SOFT_PENALTY_TAGS = {"text": 8.0, "english text": 6.0, "manga page": 10.0, "watermark": 6.0, "comic": 8.0}
OFFICIAL_TAGS = {
    "official art", "official card illustration", "key visual", "novel illustration",
    "book cover", "chapter cover", "official character information", "splash art",
}
FANART_TAGS = {"fanart", "fanart from pixiv", "fanart from x twitter", "fanart from deviantart"}
TARGET_RATIO = 2.0 / 3.0
MIN_SOURCE_RATIO = 0.50
MAX_SOURCE_RATIO = 0.86
MIN_CROP_RETENTION = 0.82
MIN_WIDTH = 1000
MIN_HEIGHT = 1400
MIN_SCORE = 72.0
MAX_DETAIL_REQUESTS = 10
REQUEST_DELAY = 1.1


@dataclass(frozen=True)
class Candidate:
    zerochan_id: int
    primary: str
    full_url: str
    source_url: str
    width: int
    height: int
    favorites: int
    tags: tuple[str, ...]
    score: float
    primary_match: float
    series_match: float
    official: bool
    fanart: bool
    solo: bool
    crop_retention: float
    reasons: tuple[str, ...]


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def tokens(value: Any) -> set[str]:
    return {x for x in normalize(value).split() if len(x) >= 2}


def similarity(target: Any, candidate: Any) -> float:
    a = normalize(target)
    b = normalize(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    at = tokens(a)
    bt = tokens(b)
    if not at or not bt:
        return 0.0
    intersection = len(at & bt)
    union = len(at | bt)
    jaccard = intersection / union if union else 0.0
    containment = intersection / len(at)
    reverse = intersection / len(bt)
    return max(jaccard, containment * 0.98, reverse * 0.90)


def crop_retention(width: int, height: int) -> float:
    if width <= 0 or height <= 0 or width >= height:
        return 0.0
    ratio = width / height
    if ratio >= TARGET_RATIO:
        return TARGET_RATIO / ratio
    return ratio / TARGET_RATIO


def _tag_norms(tags: Iterable[Any]) -> set[str]:
    return {normalize(x) for x in tags if normalize(x)}


def _series_targets(anime_title: str) -> tuple[str, ...]:
    normalized = normalize(anime_title)
    aliases = SERIES_ALIASES.get(normalized)
    if aliases:
        return tuple(normalize(x) for x in aliases)
    return (normalized,)


def _best_series_match(anime_title: str, tags: Iterable[str], detail: dict[str, Any]) -> float:
    candidates = list(tags)
    for key in ("anime", "manga", "game"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    targets = _series_targets(anime_title)
    return max((similarity(target, candidate) for target in targets for candidate in candidates), default=0.0)


def _full_url(detail: dict[str, Any], primary: str, entry_id: int) -> str:
    for key in ("full", "large", "url", "image"):
        value = str(detail.get(key) or "").strip()
        if value.startswith("https://"):
            return value
    safe_primary = re.sub(r"\s+", ".", primary.strip())
    safe_primary = quote(safe_primary, safe=".()_-'!")
    return f"https://static.zerochan.net/{safe_primary}.full.{entry_id}.png" if primary else ""


def evaluate_candidate(detail: dict[str, Any], character: dict[str, Any]) -> tuple[Candidate | None, str]:
    entry_id = int(detail.get("id") or 0)
    if entry_id <= 0:
        return None, "missing_id"

    width = int(detail.get("width") or 0)
    height = int(detail.get("height") or 0)
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return None, "resolution"
    if width >= height:
        return None, "not_portrait"

    ratio = width / height if height else 0.0
    retention = crop_retention(width, height)
    if ratio < MIN_SOURCE_RATIO or ratio > MAX_SOURCE_RATIO or retention < MIN_CROP_RETENTION:
        return None, "crop_loss"

    raw_tags = detail.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [x.strip() for x in raw_tags.split(",") if x.strip()]
    tags = tuple(str(x).strip() for x in raw_tags if str(x).strip())
    normalized_tags = _tag_norms(tags)

    hard_hits = sorted(HARD_REJECT_TAGS & normalized_tags)
    if hard_hits:
        return None, f"hard_tag:{hard_hits[0]}"

    expected_tag = str(character.get("zerochan_tag") or character.get("name") or "").strip()
    primary = str(detail.get("primary") or detail.get("tag") or "").strip()
    p_match = similarity(expected_tag, primary)
    if p_match < 0.76:
        return None, "primary_mismatch"

    series_match = _best_series_match(str(character.get("anime") or ""), tags, detail)
    if series_match < 0.58:
        return None, "series_mismatch"

    full = _full_url(detail, primary, entry_id)
    if not full.startswith("https://"):
        return None, "missing_full_url"

    official = bool(OFFICIAL_TAGS & normalized_tags)
    fanart = bool(FANART_TAGS & normalized_tags)
    solo = "solo" in normalized_tags or "solo focus" in normalized_tags
    favorites = int(detail.get("fav") or detail.get("favorites") or 0)
    source_url = str(detail.get("source") or "").strip()

    ratio_score = max(0.0, min(1.0, retention)) * 14.0
    pixels = width * height
    resolution_score = min(12.0, math.log1p(max(1.0, pixels / 1_000_000.0)) * 6.0)
    popularity_score = min(10.0, math.log1p(max(0, favorites)) * 1.65)
    score = (
        p_match * 30.0 + series_match * 20.0 + ratio_score + resolution_score + popularity_score
        + (24.0 if official else 0.0) + (8.0 if solo else 0.0)
        + (2.0 if source_url.startswith("http") else 0.0) - (4.0 if fanart else 0.0)
    )

    reasons: list[str] = []
    if official:
        reasons.append("official")
    if solo:
        reasons.append("solo")
    if fanart:
        reasons.append("fanart")
    for tag, penalty in SOFT_PENALTY_TAGS.items():
        if tag in normalized_tags:
            score -= penalty
            reasons.append(f"penalty:{tag}")

    score = round(score, 3)
    if score < MIN_SCORE:
        return None, "low_score"

    return Candidate(
        zerochan_id=entry_id, primary=primary, full_url=full, source_url=source_url,
        width=width, height=height, favorites=favorites, tags=tags, score=score,
        primary_match=round(p_match, 4), series_match=round(series_match, 4),
        official=official, fanart=fanart, solo=solo, crop_retention=round(retention, 5),
        reasons=tuple(reasons),
    ), "approved"


class ZerochanClient:
    def __init__(self, username: str, *, delay: float = REQUEST_DELAY, timeout: float = 20.0) -> None:
        username = str(username or "").strip()
        if not username:
            raise ValueError("ZEROCHAN_USERNAME is required by Zerochan's API policy")
        self.username = username
        self.delay = max(1.0, float(delay))
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": f"SourceBaltigo-Zerochan-Curator/0.1 - {username}", "Accept": "application/json"},
        )
        self._last_request = 0.0

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ZerochanClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        query = dict(params or {})
        query["json"] = ""
        response = self.client.get(f"{ZEROCHAN_BASE_URL}{path}", params=query)
        self._last_request = time.monotonic()
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise RuntimeError(f"zerochan_rate_limited:{retry_after}")
        response.raise_for_status()
        return response.json()

    def search(self, tag: str, *, limit: int = 30) -> list[dict[str, Any]]:
        encoded = quote(tag.strip().replace(" ", "+"), safe="+().,_-'!")
        payload = self._get(
            f"/{encoded}",
            {"p": 1, "l": max(1, min(100, int(limit))), "s": "fav", "t": "0", "d": "portrait", "strict": ""},
        )
        if isinstance(payload, dict):
            items = payload.get("items") or []
        else:
            items = payload or []
        return [x for x in items if isinstance(x, dict)]

    def detail(self, entry_id: int) -> dict[str, Any]:
        payload = self._get(f"/{int(entry_id)}")
        return payload if isinstance(payload, dict) else {}


def load_characters(dataset_path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    anime_items = raw.get("items", []) if isinstance(raw, dict) else raw
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for anime in anime_items or []:
        if not isinstance(anime, dict):
            continue
        anime_id = int(anime.get("anime_id") or 0)
        anime_title = str(anime.get("anime") or "").strip()
        for ch in anime.get("characters", []) or []:
            if not isinstance(ch, dict):
                continue
            cid = int(ch.get("id") or 0)
            name = str(ch.get("name") or "").strip()
            if cid <= 0 or not name or cid in seen:
                continue
            seen.add(cid)
            out.append({
                "id": cid, "name": name, "anime_id": anime_id, "anime": anime_title,
                "anilist_image": str(ch.get("image") or "").strip(),
                "zerochan_tag": ZEROCHAN_TAG_ALIASES.get(cid, name),
            })
    return out


def load_wallhaven(path: Path = WALLHAVEN_PATH) -> dict[int, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    records = raw.get("characters", {}) if isinstance(raw, dict) else {}
    out: dict[int, dict[str, Any]] = {}
    for key, value in (records or {}).items():
        try:
            cid = int(key)
        except Exception:
            continue
        if isinstance(value, dict):
            out[cid] = value
    return out


def curate_character(client: ZerochanClient, character: dict[str, Any], *, detail_limit: int = MAX_DETAIL_REQUESTS) -> dict[str, Any]:
    search_items = client.search(character["zerochan_tag"], limit=max(20, detail_limit * 2))
    filtered = []
    for item in search_items:
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if width and height and (width < MIN_WIDTH or height < MIN_HEIGHT or width >= height):
            continue
        filtered.append(item)

    approved: list[Candidate] = []
    rejected: dict[str, int] = {}
    for item in filtered[: max(1, detail_limit)]:
        entry_id = int(item.get("id") or 0)
        if entry_id <= 0:
            continue
        detail = client.detail(entry_id)
        candidate, status = evaluate_candidate(detail, character)
        if candidate:
            approved.append(candidate)
        else:
            rejected[status] = rejected.get(status, 0) + 1

    approved.sort(key=lambda x: (x.official, x.score, x.solo, x.favorites, x.width * x.height), reverse=True)
    selected = approved[0] if approved else None
    return {
        "search_tag": character["zerochan_tag"],
        "search_results": len(search_items),
        "details_checked": min(len(filtered), max(1, detail_limit)),
        "rejected": rejected,
        "selected": asdict(selected) if selected else None,
        "top_candidates": [asdict(x) for x in approved[:3]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental Zerochan portrait curator for Source Baltigo")
    parser.add_argument("--username", default=os.getenv("ZEROCHAN_USERNAME", ""), help="Zerochan username used in the required User-Agent")
    parser.add_argument("--ids", default=",".join(str(x) for x in DEFAULT_TEST_IDS), help="Comma-separated AniList character IDs")
    parser.add_argument("--contains", default="", help="Additional name/anime filter")
    parser.add_argument("--detail-limit", type=int, default=MAX_DETAIL_REQUESTS)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--write", action="store_true", help="Write JSON comparison report to --output")
    args = parser.parse_args()

    if not str(args.username or "").strip():
        print("ERROR ZEROCHAN_USERNAME is required. Create/use a Zerochan account and set the environment variable.", file=sys.stderr)
        return 2

    all_chars = load_characters()
    wanted = {int(x) for x in str(args.ids).split(",") if x.strip().isdigit()}
    chars = [x for x in all_chars if x["id"] in wanted]
    if args.contains:
        needle = normalize(args.contains)
        chars.extend(x for x in all_chars if needle in normalize(f"{x['name']} {x['anime']}") and x not in chars)
    chars.sort(key=lambda x: (x["anime"], x["name"]))

    wallhaven = load_wallhaven()
    report = {
        "version": 1,
        "source": "zerochan-test",
        "generated_at_epoch": int(time.time()),
        "policy": {
            "strict_primary": True,
            "sort": "favorites_all_time",
            "dimensions": "portrait",
            "min_width": MIN_WIDTH,
            "min_height": MIN_HEIGHT,
            "min_score": MIN_SCORE,
            "reject_group_or_cosplay_or_screenshot": True,
            "official_art_bonus": True,
            "applies_changes": False,
        },
        "characters": {},
    }

    with ZerochanClient(args.username) as client:
        for character in chars:
            print(f"CHECK id={character['id']} {character['name']} / {character['anime']} tag={character['zerochan_tag']!r}", flush=True)
            try:
                zerochan = curate_character(client, character, detail_limit=max(1, min(15, args.detail_limit)))
                selected = zerochan.get("selected") or {}
                print(
                    f"RESULT id={character['id']} zerochan={selected.get('zerochan_id')} score={selected.get('score')} "
                    f"official={selected.get('official')} size={selected.get('width')}x{selected.get('height')}",
                    flush=True,
                )
                report["characters"][str(character["id"])] = {
                    "character": character,
                    "zerochan": zerochan,
                    "wallhaven_current": wallhaven.get(character["id"]),
                    "recommendation": "zerochan_candidate" if selected else "keep_current",
                }
            except Exception as exc:
                print(f"ERROR id={character['id']} {type(exc).__name__}: {exc}", flush=True)
                report["characters"][str(character["id"])] = {
                    "character": character,
                    "error": f"{type(exc).__name__}: {exc}",
                    "wallhaven_current": wallhaven.get(character["id"]),
                    "recommendation": "keep_current",
                }

    if args.write:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {output}", flush=True)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
