from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
ANILIST_URL = "https://graphql.anilist.co"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_franchise_gaps.json"
REQUEST_DELAY = 2.10
POPULAR_PAGES = 6
POPULAR_PER_PAGE = 50
CHAR_PAGES_PER_MEDIA = 2
CHAR_PER_PAGE = 25

FRANCHISE_RELATIONS = {
    "PREQUEL", "SEQUEL", "ALTERNATIVE", "PARENT", "SIDE_STORY", "SPIN_OFF",
}

_GENERIC_EXACT = {
    "narrator", "announcer", "waiter", "waitress", "manager", "shopkeeper",
    "employee", "staff", "reporter", "crowd", "villager", "citizen", "passerby",
    "boy", "girl", "man", "woman", "child", "student", "teacher", "doctor",
    "nurse", "guard", "soldier", "police officer", "old man", "old woman",
    "shounen", "shoujo", "otoko", "onna", "obaa chan", "ojii san",
}
_GENERIC_NUMBERED_RE = re.compile(
    r"^(?:boy|girl|man|woman|student|teacher|doctor|nurse|guard|soldier|employee|staff|reporter|waiter|waitress|manager|citizen|villager|passerby)\s+[a-z0-9]+$"
)
_GENERIC_RELATIVE_RE = re.compile(r"(?:\bno\s+(?:haha|chichi|sofu|sobo)\b|\b(?:mother|father|grandmother|grandfather)\s+of\b)")


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def generic_name(name: Any) -> bool:
    n = normalize(name)
    return (not n) or n in _GENERIC_EXACT or bool(_GENERIC_NUMBERED_RE.match(n)) or bool(_GENERIC_RELATIVE_RE.search(n))


def franchise_key(title: Any) -> str:
    """Fallback textual para remakes/temporadas que não têm relation edge direta."""
    n = normalize(title)
    n = re.sub(r"\b(?:season|part|cour)\s*\d+\b", " ", n)
    n = re.sub(r"\b\d+(?:st|nd|rd|th)\s+season\b", " ", n)
    n = re.sub(r"\bfinal season\b", " ", n)
    n = re.sub(r"\b(?:tv|ova|ona)\b", " ", n)
    n = re.sub(r"\b20\d{2}\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _load_current_catalog() -> tuple[dict[int, dict[str, Any]], set[int]]:
    module_path = ROOT / "scripts" / "audit_character_catalog.py"
    spec = importlib.util.spec_from_file_location("catalog_audit_base_franchise", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assets = module.load_assets()
    overrides = module.load_overrides()
    return module.current_catalog(assets, overrides)


class Throttle:
    def __init__(self, delay: float = REQUEST_DELAY) -> None:
        self.delay = max(0.0, float(delay))
        self.last_request = 0.0

    def post(self, client: httpx.Client, query: str) -> dict[str, Any]:
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        response = client.post(ANILIST_URL, json={"query": query}, timeout=60.0)
        self.last_request = time.monotonic()
        if response.status_code == 429:
            retry = max(2, int(response.headers.get("Retry-After") or 60))
            time.sleep(retry)
            response = client.post(ANILIST_URL, json={"query": query}, timeout=60.0)
            self.last_request = time.monotonic()
        if response.status_code >= 400:
            raise RuntimeError(f"AniList HTTP {response.status_code}: {response.text[:800]}")
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"AniList GraphQL errors: {payload['errors']}")
        return payload.get("data") or {}


def popular_query(page: int) -> str:
    return f"""
    query PopularFranchises {{
      Page(page: {int(page)}, perPage: {POPULAR_PER_PAGE}) {{
        media(type: ANIME, isAdult: false, sort: [POPULARITY_DESC]) {{
          id type format popularity favourites
          startDate {{ year month day }}
          title {{ romaji english native }}
          relations {{
            edges {{
              relationType(version: 2)
              node {{
                id type format popularity favourites
                startDate {{ year month day }}
                title {{ romaji english native }}
              }}
            }}
          }}
        }}
      }}
    }}
    """


def media_title(media: dict[str, Any]) -> str:
    title = media.get("title") or {}
    return str(title.get("english") or title.get("romaji") or title.get("native") or f"Anime {media.get('id')}").strip()


def normalize_media(media: dict[str, Any], popularity_rank: int | None = None) -> dict[str, Any]:
    return {
        "anime_id": int(media.get("id") or 0),
        "anime": media_title(media),
        "type": str(media.get("type") or ""),
        "format": str(media.get("format") or ""),
        "popularity": int(media.get("popularity") or 0),
        "favourites": int(media.get("favourites") or 0),
        "start_year": int(((media.get("startDate") or {}).get("year")) or 0),
        "popularity_rank": int(popularity_rank or 0),
    }


def fetch_popular_graph(client: httpx.Client, throttle: Throttle) -> tuple[dict[int, dict[str, Any]], dict[int, set[int]]]:
    nodes: dict[int, dict[str, Any]] = {}
    graph: dict[int, set[int]] = defaultdict(set)
    for page in range(1, POPULAR_PAGES + 1):
        data = throttle.post(client, popular_query(page))
        rows = ((data.get("Page") or {}).get("media") or [])
        for index, media in enumerate(rows):
            if not isinstance(media, dict):
                continue
            mid = int(media.get("id") or 0)
            if mid <= 0:
                continue
            rank = (page - 1) * POPULAR_PER_PAGE + index + 1
            item = normalize_media(media, rank)
            old = nodes.get(mid)
            if old is None or (not old.get("popularity_rank")):
                nodes[mid] = item
            for edge in ((media.get("relations") or {}).get("edges") or []):
                if not isinstance(edge, dict):
                    continue
                relation = str(edge.get("relationType") or "").upper()
                related = edge.get("node") or {}
                if relation not in FRANCHISE_RELATIONS or str(related.get("type") or "").upper() != "ANIME":
                    continue
                rid = int(related.get("id") or 0)
                if rid <= 0:
                    continue
                graph[mid].add(rid)
                graph[rid].add(mid)
                nodes.setdefault(rid, normalize_media(related, None))
        print(f"FRANCHISE_POPULAR_PAGE {page}/{POPULAR_PAGES}", flush=True)
    return nodes, graph


def components(graph: dict[int, set[int]], node_ids: set[int]) -> list[set[int]]:
    seen: set[int] = set()
    out: list[set[int]] = []
    for start in sorted(node_ids):
        if start in seen:
            continue
        queue = deque([start])
        comp: set[int] = set()
        while queue:
            mid = queue.popleft()
            if mid in seen:
                continue
            seen.add(mid)
            comp.add(mid)
            for nxt in graph.get(mid, set()):
                if nxt not in seen:
                    queue.append(nxt)
        out.append(comp)
    return out


def _same_title_family_candidates(nodes: dict[int, dict[str, Any]], current_anime: dict[int, dict[str, Any]]) -> dict[int, int]:
    by_key: dict[str, list[int]] = defaultdict(list)
    for aid, row in current_anime.items():
        key = franchise_key(row.get("anime"))
        if key:
            by_key[key].append(aid)
    matches: dict[int, int] = {}
    for mid, row in nodes.items():
        key = franchise_key(row.get("anime"))
        current = by_key.get(key) or []
        if current:
            matches[mid] = max(current, key=lambda aid: len((current_anime.get(aid) or {}).get("characters") or {}))
    return matches


def choose_current_target(current_ids: set[int], current_anime: dict[int, dict[str, Any]]) -> int:
    return max(current_ids, key=lambda aid: (len((current_anime.get(aid) or {}).get("characters") or {}), -int(aid)))


def choose_missing_representative(component_ids: set[int], nodes: dict[int, dict[str, Any]]) -> int:
    choices = [nodes[mid] for mid in component_ids if mid in nodes]
    if not choices:
        return min(component_ids)
    choices.sort(key=lambda row: (
        0 if row.get("format") == "TV" else 1,
        int(row.get("start_year") or 9999),
        int(row.get("popularity_rank") or 999999),
        -int(row.get("popularity") or 0),
    ))
    return int(choices[0]["anime_id"])


def media_characters_query(media_id: int, pages: int = CHAR_PAGES_PER_MEDIA) -> str:
    fields = []
    for idx in range(pages):
        page = idx + 1
        fields.append(f"""
          c{idx}: characters(page: {page}, perPage: {CHAR_PER_PAGE}, sort: [ROLE, RELEVANCE, ID]) {{
            edges {{
              role
              node {{ id favourites name {{ full native }} image {{ large }} }}
            }}
          }}
        """)
    return f"""
    query FranchiseCharacters {{
      Media(id: {int(media_id)}, type: ANIME) {{
        id title {{ romaji english native }} popularity
        {' '.join(fields)}
      }}
    }}
    """


def fetch_media_characters(client: httpx.Client, throttle: Throttle, media_id: int) -> list[dict[str, Any]]:
    try:
        data = throttle.post(client, media_characters_query(media_id))
    except Exception as exc:
        print(f"FRANCHISE_CHAR_ERROR media={media_id} {type(exc).__name__}: {exc}", flush=True)
        return []
    media = data.get("Media") or {}
    out: dict[int, dict[str, Any]] = {}
    for idx in range(CHAR_PAGES_PER_MEDIA):
        edges = ((media.get(f"c{idx}") or {}).get("edges") or [])
        for local_index, edge in enumerate(edges):
            node = (edge or {}).get("node") or {}
            cid = int(node.get("id") or 0)
            if cid <= 0:
                continue
            name_obj = node.get("name") or {}
            row = {
                "id": cid,
                "name": str(name_obj.get("full") or name_obj.get("native") or f"Personagem {cid}").strip(),
                "role": str((edge or {}).get("role") or "BACKGROUND").upper(),
                "favourites": int(node.get("favourites") or 0),
                "rank_in_media": idx * CHAR_PER_PAGE + local_index + 1,
                "anilist_image_reference": str(((node.get("image") or {}).get("large")) or ""),
                "source_media_id": int(media_id),
            }
            old = out.get(cid)
            if old is None:
                out[cid] = row
            else:
                role_order = {"MAIN": 3, "SUPPORTING": 2, "BACKGROUND": 1}
                if role_order.get(row["role"], 0) > role_order.get(old["role"], 0) or row["favourites"] > old["favourites"]:
                    out[cid] = row
    return list(out.values())


def character_add_decision(row: dict[str, Any]) -> str | None:
    if generic_name(row.get("name")):
        return None
    role = str(row.get("role") or "BACKGROUND").upper()
    fav = int(row.get("favourites") or 0)
    rank = int(row.get("rank_in_media") or 999999)
    if role == "MAIN" or fav >= 100 or (role == "SUPPORTING" and rank <= 15 and fav >= 20):
        return "ADD"
    if fav >= 20 or (role == "SUPPORTING" and rank <= 25):
        return "REVIEW_ADD"
    return None


def build_franchise_plan(
    nodes: dict[int, dict[str, Any]],
    graph: dict[int, set[int]],
    current_anime: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    current_ids = set(current_anime)
    top_ids = {mid for mid, row in nodes.items() if int(row.get("popularity_rank") or 0) > 0}
    textual_match = _same_title_family_candidates(nodes, current_anime)
    comps = components(graph, set(nodes))
    plans: list[dict[str, Any]] = []
    used_top: set[int] = set()

    for comp in comps:
        relevant_top = {mid for mid in comp if mid in top_ids}
        if not relevant_top:
            continue
        used_top.update(relevant_top)
        current_in_comp = comp & current_ids
        textual_targets = {textual_match[mid] for mid in relevant_top if mid in textual_match}
        if current_in_comp:
            target_id = choose_current_target(current_in_comp, current_anime)
            status = "COVERED_ENRICH"
        elif textual_targets:
            target_id = choose_current_target(textual_targets, current_anime)
            status = "COVERED_ENRICH"
        else:
            target_id = choose_missing_representative(comp, nodes)
            status = "MISSING_FRANCHISE"
        media = [nodes[mid] for mid in comp if mid in nodes]
        media.sort(key=lambda r: (int(r.get("popularity_rank") or 999999), -int(r.get("popularity") or 0)))
        missing_top_media = [r for r in media if int(r["anime_id"]) in relevant_top and int(r["anime_id"]) not in current_ids]
        if status == "COVERED_ENRICH" and not missing_top_media:
            continue
        plans.append({
            "status": status,
            "target_anime_id": target_id,
            "target_anime": (current_anime.get(target_id) or {}).get("anime") or (nodes.get(target_id) or {}).get("anime"),
            "current_component_ids": sorted(current_in_comp),
            "component_media": media,
            "missing_popular_media": missing_top_media,
        })

    # Remakes sem relation edge (ex. HxH 2011) ficam como componentes unitários;
    # textual_match garante que sejam tratados como enriquecimento da categoria atual.
    for mid in sorted(top_ids - used_top):
        row = nodes[mid]
        if mid in current_ids:
            continue
        if mid in textual_match:
            target_id = textual_match[mid]
            plans.append({
                "status": "COVERED_ENRICH",
                "target_anime_id": target_id,
                "target_anime": (current_anime.get(target_id) or {}).get("anime"),
                "current_component_ids": [target_id],
                "component_media": [row],
                "missing_popular_media": [row],
            })
        else:
            plans.append({
                "status": "MISSING_FRANCHISE",
                "target_anime_id": mid,
                "target_anime": row.get("anime"),
                "current_component_ids": [],
                "component_media": [row],
                "missing_popular_media": [row],
            })
    return plans


def enrich_plans(
    client: httpx.Client,
    throttle: Throttle,
    plans: list[dict[str, Any]],
    current_character_ids: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adds: dict[int, dict[str, Any]] = {}
    reviews: dict[int, dict[str, Any]] = {}
    for index, plan in enumerate(plans, 1):
        media_to_scan = list(plan.get("missing_popular_media") or [])
        media_to_scan.sort(key=lambda r: (int(r.get("popularity_rank") or 999999), -int(r.get("popularity") or 0)))
        # Evita varrer 8 temporadas da mesma franquia: as 3 mais populares já
        # cobrem a grande maioria dos personagens realmente relevantes.
        media_to_scan = media_to_scan[:3]
        found: dict[int, dict[str, Any]] = {}
        for media in media_to_scan:
            mid = int(media.get("anime_id") or 0)
            for row in fetch_media_characters(client, throttle, mid):
                cid = int(row["id"])
                if cid in current_character_ids:
                    continue
                old = found.get(cid)
                role_order = {"MAIN": 3, "SUPPORTING": 2, "BACKGROUND": 1}
                if old is None or role_order.get(row["role"], 0) > role_order.get(old["role"], 0) or row["favourites"] > old["favourites"]:
                    found[cid] = row
        for cid, row in found.items():
            decision = character_add_decision(row)
            if not decision:
                continue
            enriched = dict(row)
            enriched.update({
                "decision": decision,
                "target_anime_id": int(plan["target_anime_id"]),
                "target_anime": plan.get("target_anime"),
                "franchise_status": plan.get("status"),
            })
            bucket = adds if decision == "ADD" else reviews
            old = bucket.get(cid)
            if old is None or int(enriched.get("favourites") or 0) > int(old.get("favourites") or 0):
                bucket[cid] = enriched
        plan["scanned_media_ids"] = [int(x.get("anime_id") or 0) for x in media_to_scan]
        plan["new_character_candidates"] = len(found)
        print(f"FRANCHISE_PLAN {index}/{len(plans)} {plan.get('status')} target={plan.get('target_anime_id')} scanned={plan['scanned_media_ids']}", flush=True)
    add_rows = sorted(adds.values(), key=lambda r: (-int(r.get("favourites") or 0), str(r.get("name") or "")))
    review_rows = sorted(reviews.values(), key=lambda r: (-int(r.get("favourites") or 0), str(r.get("name") or "")))
    return add_rows, review_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Agrupa temporadas/franquias e acha animes/personagens importantes ausentes sem duplicar seasons.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    current_anime, current_character_ids = _load_current_catalog()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SourceBaltigo-FranchiseAudit/1.0",
    }
    throttle = Throttle()
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        nodes, graph = fetch_popular_graph(client, throttle)
        plans = build_franchise_plan(nodes, graph, current_anime)
        add_chars, review_chars = enrich_plans(client, throttle, plans, current_character_ids)

    missing = [x for x in plans if x.get("status") == "MISSING_FRANCHISE"]
    covered = [x for x in plans if x.get("status") == "COVERED_ENRICH"]

    # Componentes com mais de uma categoria atual são candidatos a consolidação,
    # mas nada é mesclado automaticamente nesta etapa.
    duplicate_components = [
        {
            "current_anime_ids": x.get("current_component_ids"),
            "recommended_target_anime_id": x.get("target_anime_id"),
            "target_anime": x.get("target_anime"),
        }
        for x in plans
        if len(x.get("current_component_ids") or []) > 1
    ]

    result = {
        "version": 1,
        "generated_at_epoch": int(time.time()),
        "policy": {
            "popular_media_scanned": POPULAR_PAGES * POPULAR_PER_PAGE,
            "season_and_sequel_categories_are_grouped": True,
            "anilist_images_are_reference_only": True,
            "automatic_add_requires_main_or_character_interest": True,
        },
        "summary": {
            "current_anime_entries": len(current_anime),
            "missing_franchise_candidates": len(missing),
            "covered_franchises_needing_enrichment": len(covered),
            "definite_character_add_candidates": len(add_chars),
            "review_character_add_candidates": len(review_chars),
            "duplicate_current_franchise_components": len(duplicate_components),
        },
        "missing_franchises": missing,
        "covered_franchise_enrichment": covered,
        "character_add_candidates": add_chars,
        "review_character_add_candidates": review_chars,
        "duplicate_current_franchises": duplicate_components,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FRANCHISE_AUDIT_SUMMARY", json.dumps(result["summary"], ensure_ascii=False, sort_keys=True), flush=True)
    print("TOP_MISSING_FRANCHISES")
    for row in missing[:30]:
        media = row.get("missing_popular_media") or []
        best = media[0] if media else {}
        print(row.get("target_anime_id"), row.get("target_anime"), "rank=", best.get("popularity_rank"), "pop=", best.get("popularity"))
    print("TOP_FRANCHISE_CHARACTER_ADDS")
    for row in add_chars[:60]:
        print(row.get("id"), row.get("name"), "/", row.get("target_anime"), "role=", row.get("role"), "fav=", row.get("favourites"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
