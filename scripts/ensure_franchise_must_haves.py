from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

ANILIST_URL = "https://graphql.anilist.co"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "catalog_franchise_gaps.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_franchise_gaps.must_haves.json"

# Personagens que uma varredura por paginação pode deixar escapar, mas cuja
# ausência é claramente errada para a franquia. Mantemos isto pequeno e
# explícito; não é uma segunda lista de catálogo.
MUST_HAVE_BY_FRANCHISE: dict[int, list[dict[str, Any]]] = {
    20: [
        {
            "id": 53901,
            "name": "Madara Uchiha",
            "target_anime": "Naruto",
            "role": "SUPPORTING",
            "source_media_id": 1735,
            "reason": "must_have_major_character",
        }
    ]
}

# O AniList consolida essas identidades em um único ID. Isto serve para a
# auditoria não sugerir duplicatas só porque o nome mais conhecido é um alias.
IDENTITY_ALIASES = {
    "3149": ["Tobi", "Obito Uchiha"],
    "3180": ["Pain", "Nagato"],
}

# Nome de exibição único e pesquisável para a proposta final. Assim continuamos
# com um único ID, mas o usuário encontra a carta pelos dois nomes conhecidos.
IDENTITY_DISPLAY_OVERRIDES = {
    "3149": "Obito Uchiha (Tobi)",
    "3180": "Nagato (Pain)",
}


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def fetch_character(client: httpx.Client, character_id: int) -> dict[str, Any]:
    query = """
    query MustHaveCharacter($id: Int!) {
      Character(id: $id) {
        id
        favourites
        siteUrl
        name { full native alternative }
        image { large }
      }
    }
    """
    response = client.post(
        ANILIST_URL,
        json={"query": query, "variables": {"id": int(character_id)}},
        timeout=45.0,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return (payload.get("data") or {}).get("Character") or {}


def apply_must_haves(payload: dict[str, Any], fetched: dict[int, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    out = dict(payload)
    additions = [dict(x) for x in (payload.get("character_add_candidates") or []) if isinstance(x, dict)]
    reviews = [dict(x) for x in (payload.get("review_character_add_candidates") or []) if isinstance(x, dict)]

    existing_ids = {
        int(row.get("id") or 0)
        for row in additions + reviews
        if int(row.get("id") or 0) > 0
    }

    inserted: list[dict[str, Any]] = []
    for target_anime_id, specs in MUST_HAVE_BY_FRANCHISE.items():
        for spec in specs:
            cid = int(spec["id"])
            if cid in existing_ids:
                continue
            live = fetched.get(cid) or {}
            name_obj = live.get("name") or {}
            name = str(name_obj.get("full") or spec.get("name") or f"Personagem {cid}").strip()
            row = {
                "id": cid,
                "name": name,
                "decision": "ADD",
                "target_anime_id": int(target_anime_id),
                "target_anime": str(spec.get("target_anime") or f"Anime {target_anime_id}"),
                "role": str(spec.get("role") or "SUPPORTING"),
                "favourites": int(live.get("favourites") or 0),
                "rank_in_media": 0,
                "source_media_id": int(spec.get("source_media_id") or target_anime_id),
                "anilist_image_reference": str(((live.get("image") or {}).get("large")) or ""),
                "anilist_site_url": str(live.get("siteUrl") or ""),
                "franchise_status": "MISSING_FRANCHISE",
                "catalog_reason": str(spec.get("reason") or "must_have_major_character"),
            }
            additions.append(row)
            inserted.append(row)
            existing_ids.add(cid)

    additions.sort(key=lambda r: (-int(r.get("favourites") or 0), str(r.get("name") or "").casefold()))
    out["character_add_candidates"] = additions
    out["review_character_add_candidates"] = reviews
    out["identity_aliases"] = IDENTITY_ALIASES
    out["identity_display_overrides"] = IDENTITY_DISPLAY_OVERRIDES

    summary = dict(out.get("summary") or {})
    summary["must_have_characters_inserted"] = len(inserted)
    summary["definite_character_add_candidates"] = len(additions)
    out["summary"] = summary
    out["must_have_insertions"] = inserted
    out["must_have_policy"] = {
        "manual_list_is_small_and_explicit": True,
        "aliases_do_not_create_duplicate_character_ids": True,
        "consolidated_names_remain_searchable": True,
        "anilist_images_are_reference_only": True,
    }
    return out, {"inserted": len(inserted), "ids": [int(x["id"]) for x in inserted]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Garante personagens must-have que a paginação de franquias pode perder.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    must_ids = sorted({int(row["id"]) for rows in MUST_HAVE_BY_FRANCHISE.values() for row in rows})
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SourceBaltigo-CatalogMustHaves/1.0",
    }
    fetched: dict[int, dict[str, Any]] = {}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        for cid in must_ids:
            fetched[cid] = fetch_character(client, cid)
            time.sleep(1.0)

    out, stats = apply_must_haves(payload, fetched)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FRANCHISE_MUST_HAVES", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
