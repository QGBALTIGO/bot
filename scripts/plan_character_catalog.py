from __future__ import annotations

import argparse
import json
import math
import os
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "personagens_anilist.txt"
OVERRIDES_PATH = ROOT / "data" / "cards_overrides.json"
DEFAULT_OUTPUT = ROOT / "data" / "character_catalog_plan.json"
ANILIST_URL = "https://graphql.anilist.co"

QUERY = r"""
query ($id: Int!, $page: Int!, $perPage: Int!) {
  Media(id: $id, type: ANIME) {
    id
    title { userPreferred romaji english }
    characters(page: $page, perPage: $perPage, sort: [ROLE, FAVOURITES_DESC, RELEVANCE]) {
      pageInfo { currentPage hasNextPage }
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


@dataclass(frozen=True)
class Target:
    pattern: str
    keep: int


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def load_dataset() -> list[dict[str, Any]]:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    return [x for x in (items or []) if isinstance(x, dict)]


def load_overrides() -> dict[str, Any]:
    try:
        raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def parse_target(raw: str) -> Target:
    value = str(raw or "").strip()
    if not value:
        raise argparse.ArgumentTypeError("target vazio")
    if ":" not in value:
        raise argparse.ArgumentTypeError("use PADRAO:QUANTIDADE, ex: 'One Piece:120'")
    pattern, keep_raw = value.rsplit(":", 1)
    try:
        keep = int(keep_raw)
    except Exception as exc:
        raise argparse.ArgumentTypeError("quantidade inválida") from exc
    if keep < 1 or keep > 250:
        raise argparse.ArgumentTypeError("quantidade deve ficar entre 1 e 250")
    return Target(pattern=pattern.strip(), keep=keep)


def match_target(anime_name: str, target: Target) -> bool:
    return normalize(target.pattern) in normalize(anime_name)


class AniListClient:
    def __init__(self, *, timeout: float = 25.0, delay: float = 0.75) -> None:
        self.delay = max(0.5, float(delay))
        self.last_request = 0.0
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "SourceBaltigo-CatalogCurator/1.0",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "AniListClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _request(self, variables: dict[str, Any]) -> dict[str, Any]:
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        response = self.client.post(ANILIST_URL, json={"query": QUERY, "variables": variables})
        self.last_request = time.monotonic()
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After") or 60)
            time.sleep(max(1.0, retry_after))
            response = self.client.post(ANILIST_URL, json={"query": QUERY, "variables": variables})
            self.last_request = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"AniList GraphQL: {payload['errors']}")
        return payload

    def ranked_characters(self, anime_id: int, *, wanted: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        per_page = 25
        max_pages = max(1, min(10, math.ceil(max(wanted, 25) / per_page) + 1))
        ranked: list[dict[str, Any]] = []
        media_meta: dict[str, Any] = {}

        for page in range(1, max_pages + 1):
            payload = self._request({"id": int(anime_id), "page": page, "perPage": per_page})
            media = ((payload.get("data") or {}).get("Media") or {})
            if not media:
                break
            media_meta = {
                "id": int(media.get("id") or anime_id),
                "title": media.get("title") or {},
            }
            connection = media.get("characters") or {}
            for edge in connection.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                node = edge.get("node") or {}
                cid = int(node.get("id") or 0)
                name = str(((node.get("name") or {}).get("full")) or "").strip()
                if cid <= 0 or not name:
                    continue
                ranked.append({
                    "id": cid,
                    "name": name,
                    "image": str(((node.get("image") or {}).get("large")) or "").strip(),
                    "role": str(edge.get("role") or "").upper(),
                    "favourites": int(node.get("favourites") or 0),
                    "rank": len(ranked) + 1,
                })
            page_info = connection.get("pageInfo") or {}
            if len(ranked) >= wanted and not bool(page_info.get("hasNextPage")):
                break
            if len(ranked) >= wanted + 25:
                break
            if not bool(page_info.get("hasNextPage")):
                break

        # Defensive de-duplication; first occurrence keeps AniList order.
        unique: list[dict[str, Any]] = []
        seen: set[int] = set()
        for row in ranked:
            cid = int(row["id"])
            if cid in seen:
                continue
            seen.add(cid)
            unique.append(row)
        return media_meta, unique


def current_characters(anime: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for ch in anime.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        cid = int(ch.get("id") or 0)
        if cid <= 0 or cid in seen:
            continue
        seen.add(cid)
        out.append({
            "id": cid,
            "name": str(ch.get("name") or "").strip(),
            "image": str(ch.get("image") or "").strip(),
        })
    return out


def choose_keep(ranked: list[dict[str, Any]], keep: int, protected_ids: set[int]) -> list[dict[str, Any]]:
    # MAIN characters are never sacrificed merely because a numeric cap was reached.
    mains = [x for x in ranked if x.get("role") == "MAIN"]
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(row: dict[str, Any]) -> None:
        cid = int(row["id"])
        if cid not in seen:
            seen.add(cid)
            selected.append(row)

    for row in mains:
        add(row)
    for row in ranked:
        if len(selected) >= max(keep, len(mains)):
            break
        add(row)
    for row in ranked:
        if int(row["id"]) in protected_ids:
            add(row)
    return selected


def plan_one(
    client: AniListClient,
    anime: dict[str, Any],
    target: Target,
    protected_ids: set[int],
) -> dict[str, Any]:
    anime_id = int(anime.get("anime_id") or 0)
    anime_name = str(anime.get("anime") or "").strip()
    current = current_characters(anime)
    current_by_id = {int(x["id"]): x for x in current}

    media, ranked = client.ranked_characters(anime_id, wanted=target.keep)
    selected = choose_keep(ranked, target.keep, protected_ids)
    keep_ids = {int(x["id"]) for x in selected}

    retire = [
        {
            "id": cid,
            "name": row.get("name") or "",
            "reason": "outside_curated_relevance_cut",
        }
        for cid, row in current_by_id.items()
        if cid not in keep_ids and cid not in protected_ids
    ]

    missing = [
        {
            "id": int(row["id"]),
            "name": row.get("name") or "",
            "image": row.get("image") or "",
            "role": row.get("role") or "",
            "favourites": int(row.get("favourites") or 0),
            "rank": int(row.get("rank") or 0),
            "anime_id": anime_id,
            "anime": anime_name,
        }
        for row in selected
        if int(row["id"]) not in current_by_id
    ]

    return {
        "anime_id": anime_id,
        "anime": anime_name,
        "anilist_title": media.get("title") or {},
        "target_pattern": target.pattern,
        "keep_limit": target.keep,
        "current_count": len(current),
        "anilist_ranked_loaded": len(ranked),
        "kept_count": len(selected),
        "retire_count": len(retire),
        "missing_important_count": len(missing),
        "keep": selected,
        "retire": retire,
        "missing_important": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan character catalog cleanup using AniList role/favourites/relevance. Does not mutate the catalog."
    )
    parser.add_argument(
        "--target",
        action="append",
        type=parse_target,
        default=[],
        help="Title substring and keep cap, e.g. --target 'One Piece:120'",
    )
    parser.add_argument("--protected-id", action="append", type=int, default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    targets: list[Target] = list(args.target or [])
    if not targets:
        targets = [Target("One Piece", 120), Target("Naruto", 80)]

    assets = load_dataset()
    overrides = load_overrides()
    already_deleted = {int(x) for x in overrides.get("deleted_characters", []) if str(x).isdigit()}
    protected_ids = {int(x) for x in args.protected_id or []}

    matched: list[tuple[dict[str, Any], Target]] = []
    used_anime_ids: set[int] = set()
    for target in targets:
        for anime in assets:
            aid = int(anime.get("anime_id") or 0)
            name = str(anime.get("anime") or "")
            if aid <= 0 or aid in used_anime_ids:
                continue
            if match_target(name, target):
                matched.append((anime, target))
                used_anime_ids.add(aid)

    if not matched:
        print("No anime entries matched the requested targets.")
        return 2

    result: dict[str, Any] = {
        "version": 1,
        "generated_at_epoch": int(time.time()),
        "source": "AniList role + favourites + relevance",
        "policy": {
            "main_characters_never_cut_by_cap": True,
            "already_deleted_characters_ignored_on_apply": sorted(already_deleted),
            "refund_coins_per_removed_copy": 1,
            "applies_changes": False,
        },
        "summary": {},
        "animes": [],
        "retired_character_ids": [],
        "missing_important_characters": [],
    }

    with AniListClient() as client:
        for anime, target in matched:
            print(f"PLAN anime_id={anime.get('anime_id')} anime={anime.get('anime')!r} current={len(anime.get('characters') or [])} keep={target.keep}", flush=True)
            try:
                planned = plan_one(client, anime, target, protected_ids)
            except Exception as exc:
                planned = {
                    "anime_id": int(anime.get("anime_id") or 0),
                    "anime": str(anime.get("anime") or ""),
                    "target_pattern": target.pattern,
                    "error": f"{type(exc).__name__}: {exc}",
                    "current_count": len(anime.get("characters") or []),
                    "retire": [],
                    "missing_important": [],
                }
            result["animes"].append(planned)
            print(
                f"RESULT anime={planned.get('anime')!r} retire={len(planned.get('retire') or [])} missing={len(planned.get('missing_important') or [])} error={planned.get('error')}",
                flush=True,
            )

    retired: dict[int, dict[str, Any]] = {}
    missing: dict[int, dict[str, Any]] = {}
    for anime in result["animes"]:
        for row in anime.get("retire") or []:
            cid = int(row.get("id") or 0)
            if cid > 0 and cid not in already_deleted:
                retired[cid] = {
                    "id": cid,
                    "name": row.get("name") or "",
                    "anime_id": int(anime.get("anime_id") or 0),
                    "anime": anime.get("anime") or "",
                    "reason": row.get("reason") or "curation",
                }
        for row in anime.get("missing_important") or []:
            cid = int(row.get("id") or 0)
            if cid > 0:
                missing[cid] = row

    result["retired_character_ids"] = sorted(retired)
    result["retired_characters"] = [retired[cid] for cid in sorted(retired)]
    result["missing_important_characters"] = [missing[cid] for cid in sorted(missing)]
    result["summary"] = {
        "matched_anime_entries": len(result["animes"]),
        "retire_characters": len(retired),
        "missing_important_characters": len(missing),
        "errors": sum(1 for x in result["animes"] if x.get("error")),
    }

    print("CATALOG_PLAN_SUMMARY", json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    for anime in result["animes"]:
        print(
            "CATALOG_PLAN_ANIME",
            json.dumps(
                {
                    "anime_id": anime.get("anime_id"),
                    "anime": anime.get("anime"),
                    "current_count": anime.get("current_count"),
                    "kept_count": anime.get("kept_count"),
                    "retire_count": anime.get("retire_count", len(anime.get("retire") or [])),
                    "missing_important_count": anime.get("missing_important_count", len(anime.get("missing_important") or [])),
                    "error": anime.get("error"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

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
