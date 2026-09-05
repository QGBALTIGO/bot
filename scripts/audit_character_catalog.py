from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "personagens_anilist.txt"
OVERRIDES_PATH = ROOT / "data" / "cards_overrides.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_audit.json"
ANILIST_URL = "https://graphql.anilist.co"
PER_PAGE = 25
MAX_MEDIA_PER_REQUEST = 8
MAX_CONNECTION_PAGES_PER_REQUEST = 40
REQUEST_DELAY = float(os.getenv("CATALOG_AUDIT_REQUEST_DELAY", "2.10"))

ROLE_WEIGHT = {
    "MAIN": 100_000.0,
    "SUPPORTING": 20_000.0,
    "BACKGROUND": 0.0,
}

# IDs explicitamente administrados não são aposentados automaticamente.
# Isso cobre personagens customizados, nomes/imagens manuais e subcategorias especiais.
def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def load_assets(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    return [x for x in (items or []) if isinstance(x, dict)]


def protected_ids(overrides: dict[str, Any]) -> set[int]:
    out: set[int] = set()
    for item in overrides.get("custom_characters", []) or []:
        if isinstance(item, dict):
            try:
                out.add(int(item.get("id") or 0))
            except Exception:
                pass
    for key in ("character_image_overrides", "character_name_overrides"):
        mapping = overrides.get(key) or {}
        if isinstance(mapping, dict):
            for raw in mapping:
                try:
                    out.add(int(raw))
                except Exception:
                    pass
    subcategories = overrides.get("subcategories") or {}
    if isinstance(subcategories, dict):
        for values in subcategories.values():
            for raw in values or []:
                try:
                    out.add(int(raw))
                except Exception:
                    pass
    return {x for x in out if x > 0}


def current_catalog(assets: list[dict[str, Any]], overrides: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], set[int]]:
    deleted_animes = {int(x) for x in overrides.get("deleted_animes", []) or [] if str(x).isdigit()}
    deleted_chars = {int(x) for x in overrides.get("deleted_characters", []) or [] if str(x).isdigit()}
    anime_map: dict[int, dict[str, Any]] = {}
    global_ids: set[int] = set()

    for anime in assets:
        try:
            anime_id = int(anime.get("anime_id") or 0)
        except Exception:
            continue
        if anime_id <= 0 or anime_id in deleted_animes:
            continue
        title = str(anime.get("anime") or f"Anime {anime_id}").strip()
        chars: dict[int, dict[str, Any]] = {}
        for ch in anime.get("characters", []) or []:
            if not isinstance(ch, dict):
                continue
            try:
                cid = int(ch.get("id") or 0)
            except Exception:
                continue
            if cid <= 0 or cid in deleted_chars:
                continue
            chars[cid] = {
                "id": cid,
                "name": str(ch.get("name") or f"Personagem {cid}").strip(),
                "image": str(ch.get("image") or "").strip(),
            }
            global_ids.add(cid)
        anime_map[anime_id] = {"anime_id": anime_id, "anime": title, "characters": chars}

    for ch in overrides.get("custom_characters", []) or []:
        if not isinstance(ch, dict):
            continue
        try:
            cid = int(ch.get("id") or 0)
            anime_id = int(ch.get("anime_id") or 0)
        except Exception:
            continue
        if cid <= 0 or anime_id <= 0 or cid in deleted_chars or anime_id in deleted_animes:
            continue
        row = anime_map.setdefault(anime_id, {"anime_id": anime_id, "anime": str(ch.get("anime") or f"Anime {anime_id}"), "characters": {}})
        row["characters"][cid] = {
            "id": cid,
            "name": str(ch.get("name") or f"Personagem {cid}").strip(),
            "image": str(ch.get("image") or "").strip(),
        }
        global_ids.add(cid)

    return anime_map, global_ids


def estimated_pages(current_count: int) -> int:
    # +2 páginas para detectar personagens importantes que ainda não estão no bot.
    return max(2, min(40, math.ceil(max(1, int(current_count)) / PER_PAGE) + 2))


def _character_connection(alias: str, page: int) -> str:
    return f"""
      {alias}: characters(page: {int(page)}, perPage: {PER_PAGE}, sort: [ROLE, RELEVANCE, ID]) {{
        pageInfo {{ hasNextPage }}
        edges {{
          role
          node {{
            id
            favourites
            name {{ full native alternative }}
            image {{ large }}
          }}
        }}
      }}
    """


def build_batch_query(batch: list[tuple[int, int, int]]) -> tuple[str, dict[str, tuple[int, int]]]:
    # batch: (anime_id, start_page, page_count)
    blocks: list[str] = []
    aliases: dict[str, tuple[int, int]] = {}
    for media_index, (anime_id, start_page, page_count) in enumerate(batch):
        media_alias = f"m{media_index}"
        page_fields: list[str] = []
        for offset in range(page_count):
            page = start_page + offset
            page_alias = f"c{offset}"
            page_fields.append(_character_connection(page_alias, page))
        aliases[media_alias] = (anime_id, start_page)
        blocks.append(
            f"""
            {media_alias}: Media(id: {int(anime_id)}, type: ANIME) {{
              id
              popularity
              favourites
              title {{ romaji english native }}
              {' '.join(page_fields)}
            }}
            """
        )
    return "query CatalogAudit {\n" + "\n".join(blocks) + "\n}", aliases


def make_batches(anime_map: dict[int, dict[str, Any]]) -> list[list[tuple[int, int, int]]]:
    jobs = [
        (anime_id, 1, estimated_pages(len(row.get("characters") or {})))
        for anime_id, row in sorted(anime_map.items())
    ]
    batches: list[list[tuple[int, int, int]]] = []
    current: list[tuple[int, int, int]] = []
    pages = 0
    for job in jobs:
        needed = int(job[2])
        if current and (len(current) >= MAX_MEDIA_PER_REQUEST or pages + needed > MAX_CONNECTION_PAGES_PER_REQUEST):
            batches.append(current)
            current = []
            pages = 0
        current.append(job)
        pages += needed
    if current:
        batches.append(current)
    return batches


def target_size(popularity: int, total_live: int) -> int:
    pop = max(0, int(popularity or 0))
    if pop >= 1_500_000:
        target = 140
    elif pop >= 700_000:
        target = 110
    elif pop >= 300_000:
        target = 90
    elif pop >= 150_000:
        target = 75
    elif pop >= 75_000:
        target = 60
    elif pop >= 30_000:
        target = 50
    else:
        target = 40
    return min(max(20, target), max(1, int(total_live or 0)))


def importance_score(role: str, favourites: int, relevance_rank: int) -> float:
    role_key = str(role or "BACKGROUND").upper()
    fav = max(0, int(favourites or 0))
    rank = max(1, int(relevance_rank or 1))
    return round(ROLE_WEIGHT.get(role_key, 0.0) + math.log1p(fav) * 1_500.0 + max(0.0, 1_000.0 - rank * 4.0), 3)


def classify_live_characters(media: dict[str, Any], current_ids: set[int]) -> dict[str, Any]:
    chars = list(media.get("characters") or [])
    chars.sort(key=lambda x: (-float(x.get("importance_score") or 0.0), int(x.get("relevance_rank") or 999999)))
    target = target_size(int(media.get("popularity") or 0), len(chars))
    top_ids = {int(x["id"]) for x in chars[:target]}

    by_id: dict[int, dict[str, Any]] = {}
    add_candidates: list[dict[str, Any]] = []
    for row in chars:
        cid = int(row["id"])
        role = str(row.get("role") or "BACKGROUND").upper()
        fav = int(row.get("favourites") or 0)
        rank = int(row.get("relevance_rank") or 999999)
        if cid in top_ids or role == "MAIN" or fav >= 500:
            decision = "KEEP"
        elif (role == "SUPPORTING" and fav >= 25 and rank <= target + 40) or fav >= 100:
            decision = "REVIEW"
        else:
            decision = "RETIRE"
        row = dict(row)
        row["decision"] = decision
        by_id[cid] = row

        if cid not in current_ids:
            if role == "MAIN" or fav >= 100 or rank <= 15:
                add_decision = "ADD"
            elif cid in top_ids:
                add_decision = "REVIEW_ADD"
            else:
                continue
            candidate = dict(row)
            candidate["decision"] = add_decision
            add_candidates.append(candidate)

    return {
        "target_size": target,
        "characters": by_id,
        "add_candidates": add_candidates,
    }


def parse_media_payload(raw: dict[str, Any], anime_id: int, start_page: int) -> tuple[dict[str, Any] | None, bool]:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None, False
    title_obj = raw.get("title") or {}
    title = str(title_obj.get("english") or title_obj.get("romaji") or title_obj.get("native") or f"Anime {anime_id}")
    characters: list[dict[str, Any]] = []
    last_has_next = False
    page_aliases = sorted(
        (key for key in raw.keys() if key.startswith("c") and key[1:].isdigit()),
        key=lambda key: int(key[1:]),
    )
    for alias in page_aliases:
        connection = raw.get(alias) or {}
        offset = int(alias[1:])
        page = start_page + offset
        edges = connection.get("edges") or []
        for edge_index, edge in enumerate(edges):
            node = (edge or {}).get("node") or {}
            try:
                cid = int(node.get("id") or 0)
            except Exception:
                continue
            if cid <= 0:
                continue
            name_obj = node.get("name") or {}
            name = str(name_obj.get("full") or name_obj.get("native") or f"Personagem {cid}").strip()
            rank = (page - 1) * PER_PAGE + edge_index + 1
            favourites = int(node.get("favourites") or 0)
            role = str((edge or {}).get("role") or "BACKGROUND").upper()
            characters.append({
                "id": cid,
                "name": name,
                "role": role,
                "favourites": favourites,
                "relevance_rank": rank,
                "importance_score": importance_score(role, favourites, rank),
                "anilist_image": str(((node.get("image") or {}).get("large")) or ""),
            })
        last_has_next = bool((connection.get("pageInfo") or {}).get("hasNextPage"))
    return {
        "anime_id": int(raw.get("id") or anime_id),
        "anime": title,
        "popularity": int(raw.get("popularity") or 0),
        "favourites": int(raw.get("favourites") or 0),
        "characters": characters,
    }, last_has_next


def fetch_live_catalog(client: httpx.Client, anime_map: dict[int, dict[str, Any]], *, request_delay: float = REQUEST_DELAY) -> dict[int, dict[str, Any]]:
    collected: dict[int, dict[str, Any]] = {}
    overflow: list[tuple[int, int, int]] = []
    batches = make_batches(anime_map)
    for batch_index, batch in enumerate(batches, 1):
        query, aliases = build_batch_query(batch)
        response = client.post(ANILIST_URL, json={"query": query}, timeout=60.0)
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"AniList GraphQL errors: {payload['errors']}")
        data = payload.get("data") or {}
        for media_alias, (anime_id, start_page) in aliases.items():
            parsed, has_next = parse_media_payload(data.get(media_alias) or {}, anime_id, start_page)
            if parsed is None:
                continue
            previous = collected.get(anime_id)
            if previous:
                known = {int(x["id"]) for x in previous["characters"]}
                previous["characters"].extend(x for x in parsed["characters"] if int(x["id"]) not in known)
            else:
                collected[anime_id] = parsed
            if has_next:
                page_count = int(next(job[2] for job in batch if int(job[0]) == anime_id))
                overflow.append((anime_id, start_page + page_count, 5))
        print(f"ANILIST_BATCH {batch_index}/{len(batches)} media={len(batch)}", flush=True)
        if batch_index < len(batches):
            time.sleep(max(0.0, float(request_delay)))

    # Overflow é raro e cobre catálogos cuja base atual estava muito incompleta.
    safety_round = 0
    while overflow and safety_round < 8:
        safety_round += 1
        next_overflow: list[tuple[int, int, int]] = []
        for index in range(0, len(overflow), MAX_MEDIA_PER_REQUEST):
            batch = overflow[index:index + MAX_MEDIA_PER_REQUEST]
            # mantém a complexidade total sob controle
            compact: list[tuple[int, int, int]] = []
            page_sum = 0
            for job in batch:
                count = min(int(job[2]), MAX_CONNECTION_PAGES_PER_REQUEST - page_sum)
                if count <= 0:
                    break
                compact.append((int(job[0]), int(job[1]), count))
                page_sum += count
            query, aliases = build_batch_query(compact)
            response = client.post(ANILIST_URL, json={"query": query}, timeout=60.0)
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(f"AniList GraphQL errors: {payload['errors']}")
            data = payload.get("data") or {}
            for media_alias, (anime_id, start_page) in aliases.items():
                parsed, has_next = parse_media_payload(data.get(media_alias) or {}, anime_id, start_page)
                if parsed is None:
                    continue
                previous = collected.setdefault(anime_id, parsed)
                if previous is not parsed:
                    known = {int(x["id"]) for x in previous["characters"]}
                    previous["characters"].extend(x for x in parsed["characters"] if int(x["id"]) not in known)
                if has_next:
                    used = int(next(job[2] for job in compact if int(job[0]) == anime_id))
                    next_overflow.append((anime_id, start_page + used, 5))
            time.sleep(max(0.0, float(request_delay)))
        overflow = next_overflow
    return collected


def build_audit(assets: list[dict[str, Any]], overrides: dict[str, Any], live: dict[int, dict[str, Any]]) -> dict[str, Any]:
    anime_map, global_current_ids = current_catalog(assets, overrides)
    protected = protected_ids(overrides)
    per_character_decisions: dict[int, list[dict[str, Any]]] = defaultdict(list)
    anime_reports: dict[str, Any] = {}
    missing_candidates: dict[int, dict[str, Any]] = {}

    for anime_id, current in sorted(anime_map.items()):
        media = live.get(anime_id)
        current_ids = set((current.get("characters") or {}).keys())
        if not media:
            for cid in current_ids:
                per_character_decisions[cid].append({"anime_id": anime_id, "decision": "REVIEW", "reason": "media_unavailable"})
            anime_reports[str(anime_id)] = {
                "anime": current.get("anime"),
                "current_count": len(current_ids),
                "live_count": 0,
                "status": "media_unavailable",
            }
            continue

        classified = classify_live_characters(media, global_current_ids)
        live_by_id = classified["characters"]
        for cid in current_ids:
            row = live_by_id.get(cid)
            if cid in protected:
                decision = "KEEP"
                reason = "protected_manual"
            elif row is None:
                decision = "REVIEW"
                reason = "not_found_in_live_media"
            else:
                decision = str(row.get("decision") or "REVIEW")
                reason = f"role={row.get('role')} fav={row.get('favourites')} rank={row.get('relevance_rank')}"
            per_character_decisions[cid].append({"anime_id": anime_id, "decision": decision, "reason": reason})

        for candidate in classified["add_candidates"]:
            cid = int(candidate["id"])
            existing = missing_candidates.get(cid)
            enriched = dict(candidate)
            enriched["anime_id"] = anime_id
            enriched["anime"] = media.get("anime") or current.get("anime")
            if existing is None or float(enriched.get("importance_score") or 0) > float(existing.get("importance_score") or 0):
                missing_candidates[cid] = enriched

        counts = defaultdict(int)
        current_rows: list[dict[str, Any]] = []
        for cid in current_ids:
            row = live_by_id.get(cid)
            if cid in protected:
                decision = "KEEP"
            elif row is None:
                decision = "REVIEW"
            else:
                decision = str(row.get("decision") or "REVIEW")
            counts[decision] += 1
            current_rows.append({
                "id": cid,
                "name": str(((current.get("characters") or {}).get(cid) or {}).get("name") or (row or {}).get("name") or cid),
                "decision": decision,
                "role": (row or {}).get("role"),
                "favourites": int((row or {}).get("favourites") or 0),
                "relevance_rank": (row or {}).get("relevance_rank"),
                "importance_score": (row or {}).get("importance_score"),
            })
        current_rows.sort(key=lambda x: (x["decision"], -(float(x.get("importance_score") or 0))))
        anime_reports[str(anime_id)] = {
            "anime": media.get("anime") or current.get("anime"),
            "popularity": int(media.get("popularity") or 0),
            "favourites": int(media.get("favourites") or 0),
            "current_count": len(current_ids),
            "live_count": len(media.get("characters") or []),
            "target_size": int(classified["target_size"]),
            "counts": dict(counts),
            "current_characters": current_rows,
            "missing_candidates": classified["add_candidates"],
        }

    retire_ids: list[int] = []
    review_ids: list[int] = []
    keep_ids: list[int] = []
    global_decisions: dict[str, Any] = {}
    for cid in sorted(global_current_ids):
        rows = per_character_decisions.get(cid) or []
        decisions = {str(x.get("decision") or "REVIEW") for x in rows}
        if cid in protected or "KEEP" in decisions:
            decision = "KEEP"
            keep_ids.append(cid)
        elif "REVIEW" in decisions or not rows:
            decision = "REVIEW"
            review_ids.append(cid)
        else:
            decision = "RETIRE"
            retire_ids.append(cid)
        global_decisions[str(cid)] = {"decision": decision, "appearances": rows}

    add_rows = sorted(
        missing_candidates.values(),
        key=lambda x: (0 if x.get("decision") == "ADD" else 1, -float(x.get("importance_score") or 0), str(x.get("name") or "")),
    )
    definite_add = [x for x in add_rows if x.get("decision") == "ADD"]
    review_add = [x for x in add_rows if x.get("decision") == "REVIEW_ADD"]

    return {
        "version": 1,
        "generated_at_epoch": int(time.time()),
        "policy": {
            "purpose": "reduce obscure characters while preserving important and manually-managed entries",
            "retirement_is_global_only_if_no_anime_marks_keep_or_review": True,
            "protected_manual_ids": len(protected),
            "coin_compensation_per_removed_copy": 1,
        },
        "summary": {
            "anime_entries": len(anime_map),
            "current_unique_characters": len(global_current_ids),
            "keep": len(keep_ids),
            "review": len(review_ids),
            "retire_candidates": len(retire_ids),
            "definite_add_candidates": len(definite_add),
            "review_add_candidates": len(review_add),
            "projected_unique_after_retire_before_add": len(global_current_ids) - len(retire_ids),
            "projected_unique_after_definite_add": len(global_current_ids) - len(retire_ids) + len(definite_add),
        },
        "retire_ids": retire_ids,
        "review_ids": review_ids,
        "keep_ids": keep_ids,
        "add_candidates": definite_add,
        "review_add_candidates": review_add,
        "global_decisions": global_decisions,
        "anime_reports": anime_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita o catálogo inteiro do Source usando papel e popularidade do AniList, sem usar suas imagens como destino final.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--anime-ids", default="", help="Opcional: IDs de anime separados por vírgula para um lote menor.")
    parser.add_argument("--request-delay", type=float, default=REQUEST_DELAY)
    args = parser.parse_args()

    assets = load_assets()
    overrides = load_overrides()
    anime_map, _ = current_catalog(assets, overrides)
    if args.anime_ids:
        wanted = {int(x) for x in args.anime_ids.split(",") if x.strip().isdigit()}
        anime_map = {k: v for k, v in anime_map.items() if k in wanted}
        assets = [x for x in assets if int(x.get("anime_id") or 0) in wanted]

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SourceBaltigo-CatalogAudit/1.0",
    }
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        live = fetch_live_catalog(client, anime_map, request_delay=max(0.0, float(args.request_delay)))

    audit = build_audit(assets, overrides, live)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_AUDIT_SUMMARY", json.dumps(audit["summary"], ensure_ascii=False, sort_keys=True), flush=True)

    # Destaques úteis para inspeção rápida no CI.
    reports = list((audit.get("anime_reports") or {}).items())
    reports.sort(key=lambda item: -int((item[1] or {}).get("current_count") or 0))
    for anime_id, report in reports[:20]:
        print(
            "ANIME_AUDIT",
            anime_id,
            report.get("anime"),
            "current=", report.get("current_count"),
            "target=", report.get("target_size"),
            "counts=", json.dumps(report.get("counts") or {}, ensure_ascii=False, sort_keys=True),
            "missing=", len(report.get("missing_candidates") or []),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
