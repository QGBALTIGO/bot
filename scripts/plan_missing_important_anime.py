from __future__ import annotations

import argparse
import json
import math
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "personagens_anilist.txt"
DEFAULT_OUTPUT = ROOT / "data" / "missing_important_anime_plan.json"
ANILIST_URL = "https://graphql.anilist.co"

SEARCH_QUERY = r"""
query ($search: String!) {
  Media(search: $search, type: ANIME, sort: [POPULARITY_DESC]) {
    id
    title { userPreferred romaji english }
    bannerImage
    coverImage { extraLarge large }
    popularity
    favourites
    format
    status
  }
}
"""

CHARACTERS_QUERY = r"""
query ($id: Int!, $page: Int!, $perPage: Int!) {
  Media(id: $id, type: ANIME) {
    id
    title { userPreferred romaji english }
    characters(page: $page, perPage: $perPage, sort: [ROLE, FAVOURITES_DESC, RELEVANCE]) {
      pageInfo { hasNextPage }
      edges {
        role
        node {
          id
          name { full }
          image { large }
          favourites
        }
      }
    }
  }
}
"""

GENERIC_CHARACTER_NAMES = {
    "narrator",
    "announcer",
    "commentator",
    "spectator",
    "male student",
    "female student",
    "student",
    "teacher",
    "boy",
    "girl",
    "man",
    "woman",
    "citizen",
    "villager",
}


@dataclass(frozen=True)
class RequestedAnime:
    search: str
    keep: int


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def parse_requested(raw: str) -> RequestedAnime:
    value = str(raw or "").strip()
    if ":" not in value:
        raise argparse.ArgumentTypeError("use NOME:QUANTIDADE, ex: 'Naruto:80'")
    search, keep_raw = value.rsplit(":", 1)
    try:
        keep = int(keep_raw)
    except Exception as exc:
        raise argparse.ArgumentTypeError("quantidade inválida") from exc
    if not search.strip() or keep < 1 or keep > 250:
        raise argparse.ArgumentTypeError("anime/quantidade inválidos")
    return RequestedAnime(search=search.strip(), keep=keep)


def load_dataset() -> list[dict[str, Any]]:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    return [x for x in (items or []) if isinstance(x, dict)]


class AniListClient:
    def __init__(self, delay: float = 0.75) -> None:
        self.delay = max(0.5, float(delay))
        self.last_request = 0.0
        self.client = httpx.Client(
            timeout=25.0,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "SourceBaltigo-CatalogCurator/1.0",
            },
        )

    def __enter__(self) -> "AniListClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.client.close()

    def post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        response = self.client.post(ANILIST_URL, json={"query": query, "variables": variables})
        self.last_request = time.monotonic()
        if response.status_code == 429:
            retry = float(response.headers.get("Retry-After") or 60)
            time.sleep(max(1.0, retry))
            response = self.client.post(ANILIST_URL, json={"query": query, "variables": variables})
            self.last_request = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"AniList GraphQL: {payload['errors']}")
        return payload

    def search_anime(self, search: str) -> dict[str, Any]:
        payload = self.post(SEARCH_QUERY, {"search": search})
        media = ((payload.get("data") or {}).get("Media") or {})
        if not media:
            raise RuntimeError(f"anime_not_found:{search}")
        return media

    def characters(self, anime_id: int, keep: int) -> list[dict[str, Any]]:
        per_page = 25
        max_pages = max(1, min(10, math.ceil(max(keep, 25) / per_page) + 1))
        rows: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            payload = self.post(
                CHARACTERS_QUERY,
                {"id": int(anime_id), "page": page, "perPage": per_page},
            )
            media = ((payload.get("data") or {}).get("Media") or {})
            connection = media.get("characters") or {}
            for edge in connection.get("edges") or []:
                node = (edge or {}).get("node") or {}
                cid = int(node.get("id") or 0)
                name = str(((node.get("name") or {}).get("full")) or "").strip()
                if cid <= 0 or not name:
                    continue
                rows.append({
                    "id": cid,
                    "name": name,
                    "image": str(((node.get("image") or {}).get("large")) or "").strip(),
                    "role": str((edge or {}).get("role") or "").upper(),
                    "favourites": int(node.get("favourites") or 0),
                    "rank": len(rows) + 1,
                })
            if len(rows) >= keep + 25:
                break
            if not bool((connection.get("pageInfo") or {}).get("hasNextPage")):
                break

        unique: list[dict[str, Any]] = []
        seen: set[int] = set()
        for row in rows:
            cid = int(row["id"])
            if cid in seen:
                continue
            seen.add(cid)
            unique.append(row)
        return unique


def choose_characters(rows: list[dict[str, Any]], keep: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()

    def eligible(row: dict[str, Any]) -> bool:
        name = normalize(row.get("name"))
        if name in GENERIC_CHARACTER_NAMES:
            return False
        # MAIN characters always qualify. For supporting roles, require at least a little
        # real user interest so unnamed/background entries do not occupy the catalog.
        if row.get("role") == "MAIN":
            return True
        return int(row.get("favourites") or 0) >= 10

    for row in rows:
        if not eligible(row):
            continue
        cid = int(row["id"])
        if cid in seen:
            continue
        seen.add(cid)
        selected.append(row)
        if len(selected) >= keep:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan missing important anime and a curated character roster from AniList.")
    parser.add_argument("--anime", action="append", type=parse_requested, default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    requested: list[RequestedAnime] = list(args.anime or [])
    if not requested:
        requested = [RequestedAnime("Naruto", 80), RequestedAnime("Naruto: Shippuden", 100)]

    assets = load_dataset()
    existing_anime_ids = {int(x.get("anime_id") or 0) for x in assets if int(x.get("anime_id") or 0) > 0}
    existing_character_ids: set[int] = set()
    for anime in assets:
        for ch in anime.get("characters") or []:
            if not isinstance(ch, dict):
                continue
            cid = int(ch.get("id") or 0)
            if cid > 0:
                existing_character_ids.add(cid)

    result: dict[str, Any] = {
        "version": 1,
        "generated_at_epoch": int(time.time()),
        "source": "AniList popularity + role + favourites + relevance",
        "applies_changes": False,
        "animes": [],
        "summary": {},
    }

    with AniListClient() as client:
        for req in requested:
            print(f"DISCOVER search={req.search!r} keep={req.keep}", flush=True)
            try:
                media = client.search_anime(req.search)
                aid = int(media.get("id") or 0)
                ranked = client.characters(aid, req.keep)
                selected = choose_characters(ranked, req.keep)
                title_obj = media.get("title") or {}
                title = str(title_obj.get("userPreferred") or title_obj.get("romaji") or req.search).strip()
                row = {
                    "requested_search": req.search,
                    "anime_id": aid,
                    "anime": title,
                    "already_in_catalog": aid in existing_anime_ids,
                    "popularity": int(media.get("popularity") or 0),
                    "favourites": int(media.get("favourites") or 0),
                    "format": media.get("format"),
                    "status": media.get("status"),
                    "banner_image": str(media.get("bannerImage") or "").strip(),
                    "cover_image": str(((media.get("coverImage") or {}).get("extraLarge") or (media.get("coverImage") or {}).get("large")) or "").strip(),
                    "requested_keep": req.keep,
                    "selected_count": len(selected),
                    "characters": [
                        {
                            **ch,
                            "anime_id": aid,
                            "anime": title,
                            "already_in_catalog": int(ch["id"]) in existing_character_ids,
                        }
                        for ch in selected
                    ],
                }
                row["new_character_count"] = sum(1 for x in row["characters"] if not x["already_in_catalog"])
                result["animes"].append(row)
                print(
                    "MISSING_ANIME_RESULT",
                    json.dumps(
                        {
                            "search": req.search,
                            "anime_id": aid,
                            "anime": title,
                            "already_in_catalog": row["already_in_catalog"],
                            "selected": len(selected),
                            "new_characters": row["new_character_count"],
                            "popularity": row["popularity"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
                print(
                    "TOP_CHARACTERS",
                    title,
                    " | ".join(
                        f"{x['name']}[{x['role']},{x['favourites']}★]"
                        for x in selected[:25]
                    ),
                    flush=True,
                )
            except Exception as exc:
                result["animes"].append({
                    "requested_search": req.search,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                print(f"ERROR search={req.search!r} {type(exc).__name__}: {exc}", flush=True)

    result["summary"] = {
        "requested": len(requested),
        "resolved": sum(1 for x in result["animes"] if not x.get("error")),
        "missing_animes": sum(1 for x in result["animes"] if not x.get("error") and not x.get("already_in_catalog")),
        "new_characters": sum(int(x.get("new_character_count") or 0) for x in result["animes"]),
        "errors": sum(1 for x in result["animes"] if x.get("error")),
    }
    print("MISSING_ANIME_SUMMARY", json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))

    if args.write:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["summary"]["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
