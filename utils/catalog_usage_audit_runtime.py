from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from psycopg.rows import dict_row

from utils.catalog_impact_manifest import candidate_ids_hash, decode_candidate_manifest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/QGBALTIGO/bot/"
    "catalog-cleanup-v1/data/catalog_cleanup_retire_candidates.v1.json"
)
EXPECTED_CANDIDATE_COUNT = 4311
EXPECTED_CANDIDATE_SHA256 = "597fbd838e4ba01be19209c663408d992ccb9dc5b3a947fd69752804d7895dbe"
DEFAULT_OWNER_THRESHOLD = 10
DEFAULT_COPY_THRESHOLD = 20


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except Exception:
        return 0
    return number if number > 0 else 0


def _fetch_manifest() -> tuple[dict[str, Any], list[int]]:
    url = str(os.getenv("CATALOG_USAGE_MANIFEST_URL") or DEFAULT_MANIFEST_URL).strip()
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise RuntimeError("CATALOG_USAGE_MANIFEST_URL precisa apontar para raw.githubusercontent.com")

    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "SourceBaltigo-CatalogUsageAudit/1.0"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        manifest = response.json()

    if not isinstance(manifest, dict):
        raise RuntimeError("manifesto remoto inválido")
    candidate_ids = decode_candidate_manifest(manifest)
    if len(candidate_ids) != EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError(
            f"candidate_count inesperado: {len(candidate_ids)} != {EXPECTED_CANDIDATE_COUNT}"
        )
    actual_hash = candidate_ids_hash(candidate_ids)
    if actual_hash != EXPECTED_CANDIDATE_SHA256:
        raise RuntimeError(f"candidate hash inesperado: {actual_hash}")
    return manifest, candidate_ids


def _load_labels(candidate_ids: set[int]) -> dict[int, dict[str, Any]]:
    path = ROOT / "data" / "personagens_anilist.txt"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = raw.get("items", []) if isinstance(raw, dict) else raw
    labels: dict[int, dict[str, Any]] = {}
    for anime in items or []:
        if not isinstance(anime, dict):
            continue
        anime_name = str(anime.get("anime") or "").strip()
        for ch in anime.get("characters") or []:
            if not isinstance(ch, dict):
                continue
            cid = _positive_int(ch.get("id"))
            if cid <= 0 or cid not in candidate_ids:
                continue
            labels.setdefault(
                cid,
                {
                    "name": str(ch.get("name") or f"Personagem {cid}").strip(),
                    "anime": anime_name,
                },
            )
    return labels


def partition_by_usage(
    candidate_ids: set[int],
    usage_rows: list[dict[str, Any]],
    *,
    owner_threshold: int = DEFAULT_OWNER_THRESHOLD,
    copy_threshold: int = DEFAULT_COPY_THRESHOLD,
) -> tuple[set[int], list[dict[str, int]]]:
    saved: list[dict[str, int]] = []
    saved_ids: set[int] = set()
    for row in usage_rows:
        cid = _positive_int(row.get("character_id"))
        if cid <= 0 or cid not in candidate_ids:
            continue
        owners = max(0, int(row.get("owners") or 0))
        copies = max(0, int(row.get("copies") or 0))
        if owners >= int(owner_threshold) or copies >= int(copy_threshold):
            saved_ids.add(cid)
            saved.append({"character_id": cid, "owners": owners, "copies": copies})
    saved.sort(key=lambda row: (-row["owners"], -row["copies"], row["character_id"]))
    return candidate_ids - saved_ids, saved


def _summary(cur, character_ids: list[int]) -> dict[str, int]:
    if not character_ids:
        return {"affected_users": 0, "copies": 0, "owner_character_links": 0}
    cur.execute(
        """
        SELECT
            COUNT(DISTINCT user_id)::BIGINT AS affected_users,
            COALESCE(SUM(quantity), 0)::BIGINT AS copies,
            COUNT(*)::BIGINT AS owner_character_links
        FROM user_card_collection
        WHERE quantity > 0
          AND character_id = ANY(%s)
        """,
        (character_ids,),
    )
    row = dict(cur.fetchone() or {})
    return {
        "affected_users": max(0, int(row.get("affected_users") or 0)),
        "copies": max(0, int(row.get("copies") or 0)),
        "owner_character_links": max(0, int(row.get("owner_character_links") or 0)),
    }


def run_readonly_usage_audit() -> dict[str, Any]:
    manifest, candidate_list = _fetch_manifest()
    candidate_ids = set(candidate_list)
    policy = manifest.get("policy") or {}
    owner_threshold = max(1, int(policy.get("owner_review_threshold") or DEFAULT_OWNER_THRESHOLD))
    copy_threshold = max(1, int(policy.get("copy_review_threshold") or DEFAULT_COPY_THRESHOLD))

    from database_core import pool

    with pool.connection() as conn:
        try:
            conn.rollback()
        except Exception:
            pass
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("BEGIN READ ONLY")
            cur.execute(
                """
                SELECT
                    character_id,
                    COUNT(DISTINCT user_id)::BIGINT AS owners,
                    COALESCE(SUM(quantity), 0)::BIGINT AS copies
                FROM user_card_collection
                WHERE quantity > 0
                  AND character_id = ANY(%s)
                GROUP BY character_id
                ORDER BY owners DESC, copies DESC, character_id
                """,
                (candidate_list,),
            )
            usage_rows = [dict(row) for row in (cur.fetchall() or [])]
            final_retire, saved_rows = partition_by_usage(
                candidate_ids,
                usage_rows,
                owner_threshold=owner_threshold,
                copy_threshold=copy_threshold,
            )
            before = _summary(cur, candidate_list)
            final_list = sorted(final_retire)
            after = _summary(cur, final_list)
            conn.rollback()

    labels = _load_labels(candidate_ids)
    saved_public: list[dict[str, Any]] = []
    for row in saved_rows:
        cid = int(row["character_id"])
        label = labels.get(cid) or {}
        saved_public.append(
            {
                **row,
                "name": str(label.get("name") or f"Personagem {cid}"),
                "anime": str(label.get("anime") or ""),
            }
        )

    report = {
        "schema": "source.catalog-usage-readonly.v1",
        "read_only": True,
        "contains_user_ids": False,
        "candidate_count": len(candidate_list),
        "candidate_ids_sha256": candidate_ids_hash(candidate_list),
        "owner_review_threshold": owner_threshold,
        "copy_review_threshold": copy_threshold,
        "characters_with_any_owner": len(usage_rows),
        "saved_by_collection_count": len(saved_public),
        "saved_by_collection": saved_public,
        "final_retire_count": len(final_list),
        "final_retire_ids_sha256": candidate_ids_hash(final_list),
        "before_guard": before,
        "after_guard": after,
        "coins_required_after_guard": int(after["copies"]),
    }
    return report


def run_and_log_readonly_usage_audit() -> dict[str, Any]:
    report = run_readonly_usage_audit()
    print(
        "CATALOG_USAGE_AUDIT_RESULT "
        + json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        flush=True,
    )
    return report
