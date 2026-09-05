from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.guard_catalog_retirements_by_usage import (  # noqa: E402
    DEFAULT_COPY_REVIEW_THRESHOLD,
    DEFAULT_OWNER_REVIEW_THRESHOLD,
    run_live_usage_guard,
)
from utils.catalog_impact_manifest import load_candidate_manifest  # noqa: E402

DEFAULT_MANIFEST = ROOT / "data" / "catalog_cleanup_retire_candidates.v1.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_live_impact.json"


def manifest_policy(manifest: dict[str, Any]) -> tuple[int, int]:
    policy = manifest.get("policy") or {}
    owner_threshold = max(
        1,
        int(policy.get("owner_review_threshold") or DEFAULT_OWNER_REVIEW_THRESHOLD),
    )
    copy_threshold = max(
        1,
        int(policy.get("copy_review_threshold") or DEFAULT_COPY_REVIEW_THRESHOLD),
    )
    return owner_threshold, copy_threshold


def public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {
            "candidate_ids",
            "candidate_ids_zlib_base64",
            "candidate_ids_payload_chunks",
        }
    }


def build_report(manifest: dict[str, Any]) -> dict[str, Any]:
    owner_threshold, copy_threshold = manifest_policy(manifest)
    report = run_live_usage_guard(
        manifest["candidate_ids"],
        owner_threshold=owner_threshold,
        copy_threshold=copy_threshold,
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["manifest"] = public_manifest(manifest)
    report["read_only"] = True
    report["contains_user_ids"] = False
    return report


def compact_summary(report: dict[str, Any]) -> dict[str, Any]:
    before = report.get("before_guard") or {}
    after = report.get("after_guard") or {}
    return {
        "read_only": True,
        "candidate_count": int(report.get("candidate_count") or 0),
        "moved_to_review": int(report.get("moved_to_review_count") or 0),
        "final_retire": int(report.get("final_retire_count") or 0),
        "affected_users_before_guard": int(before.get("affected_users") or 0),
        "copies_before_guard": int(before.get("copies") or 0),
        "affected_users_after_guard": int(after.get("affected_users") or 0),
        "copies_after_guard": int(after.get("copies") or 0),
        "coins_required_after_guard": int(report.get("coins_required_after_guard") or 0),
        "candidate_ids_sha256": str(
            ((report.get("manifest") or {}).get("candidate_ids_sha256")) or ""
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Executa a trava de impacto real do catálogo contra o PostgreSQL em modo somente leitura. "
            "Não altera coleção, Coins, trades, spawns ou overrides."
        )
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    manifest = load_candidate_manifest(Path(args.manifest))
    report = build_report(manifest)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "CATALOG_IMPACT_READONLY",
        json.dumps(compact_summary(report), ensure_ascii=False, sort_keys=True),
        flush=True,
    )
    print(f"CATALOG_IMPACT_OUTPUT {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
