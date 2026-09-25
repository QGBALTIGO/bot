from __future__ import annotations

import argparse
import json
import math
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
ANILIST_URL = "https://graphql.anilist.co"
DEFAULT_INPUT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_audit_refined.json"
BATCH_SIZE = 25
REQUEST_DELAY = 2.10

# Nomes genéricos que não fazem sentido como carta colecionável por si só.
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
_GENERIC_RELATIVE_RE = re.compile(
    r"(?:\bno\s+(?:haha|chichi|sofu|sobo)\b|\b(?:mother|father|grandmother|grandfather)\s+of\b)"
)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def is_generic_character_name(name: Any) -> bool:
    n = normalize(name)
    if not n:
        return True
    if n in _GENERIC_EXACT:
        return True
    if _GENERIC_NUMBERED_RE.match(n):
        return True
    if _GENERIC_RELATIVE_RE.search(n):
        return True
    return False


def thresholds_for_media(popularity: int) -> tuple[int, int]:
    """Retorna (keep_favourites, review_favourites).

    Quanto maior a obra, maior a exigência: uma franquia gigantesca pode ter
    centenas de figurantes com 1-2 favoritos, enquanto em um anime pequeno
    2 favoritos já podem indicar um personagem reconhecível.
    """
    pop = max(0, int(popularity or 0))
    if pop >= 700_000:
        return 25, 10
    if pop >= 500_000:
        return 20, 8
    if pop >= 300_000:
        return 15, 6
    if pop >= 150_000:
        return 10, 4
    if pop >= 75_000:
        return 8, 3
    if pop >= 30_000:
        return 5, 2
    if pop >= 10_000:
        return 3, 1
    return 2, 1


def decision_for_character(
    *,
    name: str,
    role: str | None,
    favourites: int | None,
    relevance_rank: int | None,
    media_popularity: int,
    protected: bool = False,
    metadata_available: bool = True,
) -> tuple[str, str]:
    if protected:
        return "KEEP", "protected_manual"

    role_norm = str(role or "").upper() or None
    fav = max(0, int(favourites or 0))
    keep_fav, review_fav = thresholds_for_media(media_popularity)

    if is_generic_character_name(name):
        return "RETIRE", "generic_unnamed_character"

    if not metadata_available:
        return "REVIEW", "metadata_unavailable"

    if role_norm == "MAIN":
        return "KEEP", "main_character"

    if fav >= keep_fav:
        return "KEEP", f"favourites={fav}>={keep_fav}"

    if fav >= review_fav:
        return "REVIEW", f"favourites={fav}>={review_fav}"

    # Segurança extra para coadjuvantes que moderadores do AniList colocaram
    # muito cedo na conexão da obra, mesmo que tenham poucos favoritos.
    if role_norm == "SUPPORTING" and relevance_rank is not None and int(relevance_rank) <= 20:
        return "REVIEW", f"supporting_rank={int(relevance_rank)}"

    return "RETIRE", f"low_interest role={role_norm or 'unknown'} favourites={fav}"


def _global_character_query(ids: list[int]) -> str:
    joined = ",".join(str(int(x)) for x in ids)
    return f"""
    query CharacterFallbacks {{
      Page(page: 1, perPage: {len(ids)}) {{
        characters(id_in: [{joined}], sort: [ID]) {{
          id
          favourites
          name {{ full native }}
          media(page: 1, perPage: 10, type: ANIME, sort: [POPULARITY_DESC]) {{
            edges {{
              characterRole
              node {{ id popularity title {{ romaji english }} }}
            }}
          }}
        }}
      }}
    }}
    """


def fetch_global_character_fallbacks(client: httpx.Client, ids: list[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    clean_ids = sorted({int(x) for x in ids if int(x) > 0})
    for offset in range(0, len(clean_ids), BATCH_SIZE):
        batch = clean_ids[offset:offset + BATCH_SIZE]
        if not batch:
            continue
        response = client.post(ANILIST_URL, json={"query": _global_character_query(batch)}, timeout=60.0)
        if response.status_code == 429:
            retry = max(2, int(response.headers.get("Retry-After") or 60))
            time.sleep(retry)
            response = client.post(ANILIST_URL, json={"query": _global_character_query(batch)}, timeout=60.0)
        if response.status_code >= 400:
            print(f"CHAR_FALLBACK_HTTP_ERROR status={response.status_code} offset={offset} body={response.text[:600]}", flush=True)
            time.sleep(REQUEST_DELAY)
            continue
        payload = response.json()
        for ch in (((payload.get("data") or {}).get("Page") or {}).get("characters") or []):
            if not isinstance(ch, dict):
                continue
            try:
                cid = int(ch.get("id") or 0)
            except Exception:
                continue
            if cid <= 0:
                continue
            roles: list[str] = []
            media_rows: list[dict[str, Any]] = []
            for edge in ((ch.get("media") or {}).get("edges") or []):
                if not isinstance(edge, dict):
                    continue
                role = str(edge.get("characterRole") or "").upper()
                if role:
                    roles.append(role)
                node = edge.get("node") or {}
                if isinstance(node, dict):
                    media_rows.append(node)
            if "MAIN" in roles:
                best_role = "MAIN"
            elif "SUPPORTING" in roles:
                best_role = "SUPPORTING"
            elif "BACKGROUND" in roles:
                best_role = "BACKGROUND"
            else:
                best_role = None
            name_obj = ch.get("name") or {}
            out[cid] = {
                "id": cid,
                "name": str(name_obj.get("full") or name_obj.get("native") or "").strip(),
                "favourites": int(ch.get("favourites") or 0),
                "best_role_any_anime": best_role,
                "media": media_rows,
            }
        print(f"CHAR_FALLBACK_BATCH {offset // BATCH_SIZE + 1}/{math.ceil(len(clean_ids) / BATCH_SIZE)} size={len(batch)}", flush=True)
        if offset + BATCH_SIZE < len(clean_ids):
            time.sleep(REQUEST_DELAY)
    return out


def _load_protected_ids() -> set[int]:
    # Import local para reaproveitar a regra já testada pelo auditor principal.
    import importlib.util
    module_path = ROOT / "scripts" / "audit_character_catalog.py"
    spec = importlib.util.spec_from_file_location("catalog_audit_base", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    overrides = module.load_overrides()
    return set(module.protected_ids(overrides))


def refine(raw: dict[str, Any], fallback: dict[int, dict[str, Any]], protected_ids: set[int]) -> dict[str, Any]:
    reports = raw.get("anime_reports") or {}
    global_rows: dict[int, list[dict[str, Any]]] = {}

    for anime_id, report in reports.items():
        if not isinstance(report, dict):
            continue
        popularity = int(report.get("popularity") or 0)
        counts = {"KEEP": 0, "REVIEW": 0, "RETIRE": 0}
        refined_rows: list[dict[str, Any]] = []
        for row in report.get("current_characters") or []:
            if not isinstance(row, dict):
                continue
            try:
                cid = int(row.get("id") or 0)
            except Exception:
                continue
            fb = fallback.get(cid) or {}
            original_role = row.get("role")
            metadata_available = original_role is not None or bool(fb)
            role = original_role or fb.get("best_role_any_anime")
            favourites = row.get("favourites")
            if original_role is None and fb:
                favourites = int(fb.get("favourites") or 0)
            name = str(row.get("name") or fb.get("name") or f"Personagem {cid}").strip()
            decision, reason = decision_for_character(
                name=name,
                role=role,
                favourites=int(favourites or 0),
                relevance_rank=row.get("relevance_rank"),
                media_popularity=popularity,
                protected=cid in protected_ids,
                metadata_available=metadata_available,
            )
            enriched = dict(row)
            enriched.update({
                "name": name,
                "role": role,
                "favourites": int(favourites or 0),
                "decision": decision,
                "decision_reason": reason,
                "global_fallback_used": original_role is None and bool(fb),
            })
            refined_rows.append(enriched)
            counts[decision] += 1
            global_rows.setdefault(cid, []).append({
                "anime_id": int(anime_id),
                "decision": decision,
                "reason": reason,
            })

        # Se o base-audit não conseguiu consultar a mídia, ele não gera current_characters.
        # Mantemos tudo em REVIEW via global_decisions original, nunca aposentamos às cegas.
        report["current_characters"] = sorted(
            refined_rows,
            key=lambda x: ({"KEEP": 0, "REVIEW": 1, "RETIRE": 2}.get(x.get("decision"), 9), -int(x.get("favourites") or 0), str(x.get("name") or "")),
        )
        report["counts"] = counts
        keep_fav, review_fav = thresholds_for_media(popularity)
        report["refined_policy"] = {
            "keep_favourites": keep_fav,
            "review_favourites": review_fav,
            "main_always_kept": True,
            "generic_names_retired": True,
        }
        report["recommended_total_after_review"] = counts["KEEP"] + counts["REVIEW"]

    original_global = raw.get("global_decisions") or {}
    all_ids = {int(k) for k in original_global if str(k).isdigit()} | set(global_rows)
    keep_ids: list[int] = []
    review_ids: list[int] = []
    retire_ids: list[int] = []
    refined_global: dict[str, Any] = {}
    for cid in sorted(all_ids):
        appearances = global_rows.get(cid) or []
        if cid in protected_ids:
            decision = "KEEP"
            appearances = appearances or [{"decision": "KEEP", "reason": "protected_manual"}]
        elif not appearances:
            decision = "REVIEW"
            appearances = (original_global.get(str(cid)) or {}).get("appearances") or [{"decision": "REVIEW", "reason": "no_refined_media_row"}]
        else:
            values = {str(x.get("decision") or "REVIEW") for x in appearances}
            if "KEEP" in values:
                decision = "KEEP"
            elif "REVIEW" in values:
                decision = "REVIEW"
            else:
                decision = "RETIRE"
        if decision == "KEEP":
            keep_ids.append(cid)
        elif decision == "RETIRE":
            retire_ids.append(cid)
        else:
            review_ids.append(cid)
        refined_global[str(cid)] = {"decision": decision, "appearances": appearances}

    # Limpa sugestões automáticas claramente inúteis (Narrator, Waiter, mãe sem nome etc.).
    def clean_add(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if is_generic_character_name(row.get("name")):
                continue
            out.append(row)
        return out

    definite_add = clean_add(raw.get("add_candidates") or [])
    review_add = clean_add(raw.get("review_add_candidates") or [])
    summary = dict(raw.get("summary") or {})
    summary.update({
        "keep": len(keep_ids),
        "review": len(review_ids),
        "retire_candidates": len(retire_ids),
        "definite_add_candidates": len(definite_add),
        "review_add_candidates": len(review_add),
        "projected_unique_after_retire_before_add": len(all_ids) - len(retire_ids),
        "projected_unique_after_definite_add": len(all_ids) - len(retire_ids) + len(definite_add),
    })
    raw["version"] = 3
    raw["refinement"] = {
        "policy": "character_favourites_role_and_generic_name_filter",
        "global_fallback_count": len(fallback),
        "protected_manual_ids": len(protected_ids),
        "automatic_retirement_requires_metadata": True,
    }
    raw["summary"] = summary
    raw["keep_ids"] = keep_ids
    raw["review_ids"] = review_ids
    raw["retire_ids"] = retire_ids
    raw["global_decisions"] = refined_global
    raw["add_candidates"] = definite_add
    raw["review_add_candidates"] = review_add
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Refina o audit do catálogo para remover figurantes sem sacrificar personagens conhecidos.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    unresolved: set[int] = set()
    for report in (raw.get("anime_reports") or {}).values():
        if not isinstance(report, dict):
            continue
        for row in report.get("current_characters") or []:
            if isinstance(row, dict) and row.get("role") is None:
                try:
                    unresolved.add(int(row.get("id") or 0))
                except Exception:
                    pass
    unresolved.discard(0)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SourceBaltigo-CatalogRefiner/1.0",
    }
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        fallback = fetch_global_character_fallbacks(client, sorted(unresolved)) if unresolved else {}

    refined = refine(raw, fallback, _load_protected_ids())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(refined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_REFINED_SUMMARY", json.dumps(refined.get("summary") or {}, ensure_ascii=False, sort_keys=True), flush=True)
    for aid in ("21", "269", "6702", "527", "113415"):
        row = (refined.get("anime_reports") or {}).get(aid) or {}
        if row:
            print(
                "REFINED_FOCUS", aid, row.get("anime"),
                "current=", row.get("current_count"),
                "counts=", json.dumps(row.get("counts") or {}, ensure_ascii=False, sort_keys=True),
                "recommended=", row.get("recommended_total_after_review"),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
