from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "data" / "catalog_cleanup_audit.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_audit.usage_guarded.json"
DEFAULT_OWNER_REVIEW_THRESHOLD = 10
DEFAULT_COPY_REVIEW_THRESHOLD = 20


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def int_set(values: Any) -> set[int]:
    out: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except Exception:
            continue
        if number > 0:
            out.add(number)
    return out


def load_character_labels() -> dict[int, dict[str, Any]]:
    dataset_path = ROOT / "data" / "personagens_anilist.txt"
    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    labels: dict[int, dict[str, Any]] = {}
    for anime in items or []:
        if not isinstance(anime, dict):
            continue
        anime_name = str(anime.get("anime") or "").strip()
        try:
            anime_id = int(anime.get("anime_id") or 0)
        except Exception:
            anime_id = 0
        for ch in anime.get("characters", []) or []:
            if not isinstance(ch, dict):
                continue
            try:
                cid = int(ch.get("id") or 0)
            except Exception:
                continue
            if cid <= 0:
                continue
            labels.setdefault(cid, {
                "character_id": cid,
                "name": str(ch.get("name") or f"Personagem {cid}").strip(),
                "anime_id": anime_id,
                "anime": anime_name,
            })
    return labels


def fetch_usage_rows(retire_ids: list[int]) -> list[dict[str, Any]]:
    if not retire_ids:
        return []
    from database_core import pool

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    character_id,
                    COUNT(DISTINCT user_id)::BIGINT AS owners,
                    SUM(quantity)::BIGINT AS copies
                FROM user_card_collection
                WHERE quantity > 0
                  AND character_id = ANY(%s)
                GROUP BY character_id
                ORDER BY owners DESC, copies DESC, character_id
                """,
                (retire_ids,),
            )
            return [dict(row) for row in (cur.fetchall() or [])]


def partition_by_usage(
    retire_ids: set[int],
    usage_rows: list[dict[str, Any]],
    *,
    owner_threshold: int = DEFAULT_OWNER_REVIEW_THRESHOLD,
    copy_threshold: int = DEFAULT_COPY_REVIEW_THRESHOLD,
) -> tuple[set[int], set[int], dict[int, dict[str, int]]]:
    owner_threshold = max(1, int(owner_threshold))
    copy_threshold = max(1, int(copy_threshold))
    usage: dict[int, dict[str, int]] = {}
    review_due_usage: set[int] = set()
    for row in usage_rows:
        try:
            cid = int(row.get("character_id") or 0)
        except Exception:
            continue
        if cid <= 0 or cid not in retire_ids:
            continue
        owners = max(0, int(row.get("owners") or 0))
        copies = max(0, int(row.get("copies") or 0))
        usage[cid] = {"owners": owners, "copies": copies}
        if owners >= owner_threshold or copies >= copy_threshold:
            review_due_usage.add(cid)
    final_retire = set(retire_ids) - review_due_usage
    return final_retire, review_due_usage, usage


def build_guarded_audit(
    audit: dict[str, Any],
    usage_rows: list[dict[str, Any]],
    *,
    labels: dict[int, dict[str, Any]] | None = None,
    owner_threshold: int = DEFAULT_OWNER_REVIEW_THRESHOLD,
    copy_threshold: int = DEFAULT_COPY_REVIEW_THRESHOLD,
) -> tuple[dict[str, Any], dict[str, Any]]:
    guarded = deepcopy(audit)
    original_retire = int_set(audit.get("retire_ids"))
    original_review = int_set(audit.get("review_ids"))
    final_retire, moved_to_review, usage = partition_by_usage(
        original_retire,
        usage_rows,
        owner_threshold=owner_threshold,
        copy_threshold=copy_threshold,
    )
    final_review = original_review | moved_to_review

    label_map = labels or {}
    affected_before = sum(int(data.get("copies") or 0) for data in usage.values())
    affected_after = sum(int((usage.get(cid) or {}).get("copies") or 0) for cid in final_retire)
    owners_before = sum(int(data.get("owners") or 0) for data in usage.values())

    high_impact: list[dict[str, Any]] = []
    for cid in moved_to_review:
        data = usage.get(cid) or {"owners": 0, "copies": 0}
        label = label_map.get(cid) or {}
        high_impact.append({
            "character_id": cid,
            "name": str(label.get("name") or f"Personagem {cid}"),
            "anime_id": label.get("anime_id"),
            "anime": str(label.get("anime") or ""),
            "owners": int(data.get("owners") or 0),
            "copies": int(data.get("copies") or 0),
            "decision": "REVIEW_BY_COLLECTION_IMPACT",
        })
    high_impact.sort(key=lambda row: (-int(row["owners"]), -int(row["copies"]), str(row["name"])))

    impacted_retire: list[dict[str, Any]] = []
    for cid in final_retire:
        data = usage.get(cid)
        if not data:
            continue
        label = label_map.get(cid) or {}
        impacted_retire.append({
            "character_id": cid,
            "name": str(label.get("name") or f"Personagem {cid}"),
            "anime_id": label.get("anime_id"),
            "anime": str(label.get("anime") or ""),
            "owners": int(data.get("owners") or 0),
            "copies": int(data.get("copies") or 0),
            "coins_if_retired": int(data.get("copies") or 0),
        })
    impacted_retire.sort(key=lambda row: (-int(row["owners"]), -int(row["copies"]), str(row["name"])))

    guarded["retire_ids"] = sorted(final_retire)
    guarded["review_ids"] = sorted(final_review)
    summary = dict(guarded.get("summary") or {})
    summary["retire_candidates_before_usage_guard"] = len(original_retire)
    summary["retire_candidates"] = len(final_retire)
    summary["review"] = len(final_review)
    summary["moved_to_review_by_collection_impact"] = len(moved_to_review)
    current_unique = int(summary.get("current_unique_characters") or 0)
    if current_unique:
        summary["projected_unique_after_retire_before_add"] = current_unique - len(final_retire)
        summary["projected_unique_after_definite_add"] = (
            current_unique - len(final_retire) + int(summary.get("definite_add_candidates") or 0)
        )
    guarded["summary"] = summary
    guarded["collection_impact_guard"] = {
        "owner_review_threshold": int(owner_threshold),
        "copy_review_threshold": int(copy_threshold),
        "moved_to_review": high_impact,
        "retirements_with_existing_owners": impacted_retire,
        "copies_affected_before_guard": affected_before,
        "copies_affected_after_guard": affected_after,
        "owner_character_links_before_guard": owners_before,
        "coins_required_after_guard": affected_after,
    }
    stats = {
        "original_retire": len(original_retire),
        "final_retire": len(final_retire),
        "moved_to_review": len(moved_to_review),
        "copies_affected_before_guard": affected_before,
        "copies_affected_after_guard": affected_after,
        "coins_required_after_guard": affected_after,
    }
    return guarded, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebaixa aposentadorias de alto impacto para REVIEW usando a coleção real. Somente leitura do banco."
    )
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--owner-threshold", type=int, default=DEFAULT_OWNER_REVIEW_THRESHOLD)
    parser.add_argument("--copy-threshold", type=int, default=DEFAULT_COPY_REVIEW_THRESHOLD)
    args = parser.parse_args()

    audit = load_json(Path(args.audit))
    retire_ids = sorted(int_set(audit.get("retire_ids")))
    usage_rows = fetch_usage_rows(retire_ids)
    guarded, stats = build_guarded_audit(
        audit,
        usage_rows,
        labels=load_character_labels(),
        owner_threshold=max(1, int(args.owner_threshold)),
        copy_threshold=max(1, int(args.copy_threshold)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(guarded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG_USAGE_GUARD", json.dumps(stats, ensure_ascii=False, sort_keys=True), flush=True)
    for row in (guarded.get("collection_impact_guard") or {}).get("moved_to_review", [])[:50]:
        print(
            "USAGE_REVIEW",
            row.get("character_id"), row.get("name"), "/", row.get("anime"),
            "owners=", row.get("owners"), "copies=", row.get("copies"),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
