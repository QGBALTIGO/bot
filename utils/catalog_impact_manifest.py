from __future__ import annotations

import base64
import hashlib
import json
import zlib
from pathlib import Path
from typing import Any

SUPPORTED_ENCODING = "delta-varint+zlib+base85"


def _int_set(values: Any) -> set[int]:
    out: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except Exception:
            continue
        if number > 0:
            out.add(number)
    return out


def candidate_ids_hash(values: Any) -> str:
    ids = sorted(_int_set(values))
    canonical = ",".join(str(value) for value in ids).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _decode_varints(raw: bytes) -> list[int]:
    deltas: list[int] = []
    value = 0
    shift = 0
    for byte in raw:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            if shift > 63:
                raise ValueError("varint inválido no manifesto")
            continue
        deltas.append(value)
        value = 0
        shift = 0
    if shift:
        raise ValueError("varint truncado no manifesto")

    ids: list[int] = []
    current = 0
    for delta in deltas:
        if delta <= 0:
            raise ValueError("delta inválido no manifesto")
        current += delta
        ids.append(current)
    return ids


def decode_candidate_manifest(manifest: dict[str, Any]) -> list[int]:
    if not isinstance(manifest, dict):
        raise ValueError("manifesto inválido")
    if str(manifest.get("encoding") or "") != SUPPORTED_ENCODING:
        raise ValueError("encoding de manifesto não suportado")

    chunks = manifest.get("candidate_ids_payload_chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("manifesto sem candidate_ids_payload_chunks")
    if any(not isinstance(chunk, str) or not chunk for chunk in chunks):
        raise ValueError("bloco inválido no manifesto")

    payload = "".join(chunks)
    try:
        compressed = base64.b85decode(payload.encode("ascii"))
        raw = zlib.decompress(compressed)
        ids = _decode_varints(raw)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("manifesto de candidatos corrompido") from exc

    expected_count = int(manifest.get("candidate_count") or 0)
    if expected_count <= 0 or len(ids) != expected_count:
        raise ValueError("quantidade de IDs do manifesto não confere")
    if ids != sorted(set(ids)):
        raise ValueError("IDs do manifesto não são estritamente crescentes")

    expected_hash = str(manifest.get("candidate_ids_sha256") or "").strip().lower()
    actual_hash = candidate_ids_hash(ids)
    if not expected_hash or actual_hash != expected_hash:
        raise ValueError("hash dos IDs do manifesto não confere")
    return ids


def load_candidate_manifest(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifesto inválido")
    ids = decode_candidate_manifest(raw)
    out = dict(raw)
    out["candidate_ids"] = ids
    return out
