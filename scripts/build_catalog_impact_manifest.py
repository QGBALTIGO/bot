from __future__ import annotations

import argparse
import base64
import json
import sys
import zlib
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.catalog_impact_manifest import SUPPORTED_ENCODING, candidate_ids_hash

DEFAULT_INPUT = ROOT / "data" / "catalog_cleanup_audit.final.json"
DEFAULT_OUTPUT = ROOT / "data" / "catalog_cleanup_retire_candidates.v1.json"


def _int_set(values: Any) -> list[int]:
    out: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except Exception:
            continue
        if number > 0:
            out.add(number)
    return sorted(out)


def _encode_varint(value: int) -> bytes:
    if value <= 0:
        raise ValueError("varint precisa ser positivo")
    out = bytearray()
    current = int(value)
    while True:
        byte = current & 0x7F
        current >>= 7
        if current:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode_candidate_ids(ids: list[int]) -> str:
    clean = _int_set(ids)
    previous = 0
    raw = bytearray()
    for value in clean:
        delta = int(value) - previous
        if delta <= 0:
            raise ValueError("IDs precisam ser estritamente crescentes")
        raw.extend(_encode_varint(delta))
        previous = int(value)
    compressed = zlib.compress(bytes(raw), level=9)
    return base64.b85encode(compressed).decode("ascii")


def build_manifest(
    audit: dict[str, Any],
    *,
    snapshot: str,
    source_pr: int = 40,
    owner_threshold: int = 10,
    copy_threshold: int = 20,
    chunk_size: int = 900,
) -> dict[str, Any]:
    ids = _int_set(audit.get("retire_ids"))
    if not ids:
        raise ValueError("audit final não contém retire_ids")
    payload = encode_candidate_ids(ids)
    size = max(100, int(chunk_size))
    chunks = [payload[i:i + size] for i in range(0, len(payload), size)]
    return {
        "schema_version": 3,
        "catalog_snapshot": str(snapshot),
        "source_pr": int(source_pr),
        "source_audit_version": int(audit.get("version") or 0),
        "candidate_count": len(ids),
        "candidate_ids_sha256": candidate_ids_hash(ids),
        "encoding": SUPPORTED_ENCODING,
        "candidate_ids_payload_chunks": chunks,
        "policy": {
            "owner_review_threshold": max(1, int(owner_threshold)),
            "copy_review_threshold": max(1, int(copy_threshold)),
        },
        "read_only_candidate_manifest": True,
        "note": "RETIRE final após terceira passada; ainda sujeito à trava por uso real da coleção.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera manifesto compacto do RETIRE final para /health catalog.")
    parser.add_argument("--audit", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--snapshot", default=date.today().isoformat())
    parser.add_argument("--source-pr", type=int, default=40)
    parser.add_argument("--owner-threshold", type=int, default=10)
    parser.add_argument("--copy-threshold", type=int, default=20)
    args = parser.parse_args()

    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    manifest = build_manifest(
        audit,
        snapshot=args.snapshot,
        source_pr=args.source_pr,
        owner_threshold=args.owner_threshold,
        copy_threshold=args.copy_threshold,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "CATALOG_IMPACT_MANIFEST",
        json.dumps(
            {
                "candidate_count": manifest["candidate_count"],
                "candidate_ids_sha256": manifest["candidate_ids_sha256"],
                "chunks": len(manifest["candidate_ids_payload_chunks"]),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
