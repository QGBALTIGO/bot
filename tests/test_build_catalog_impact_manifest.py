from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = load_module("build_catalog_impact_manifest", "scripts/build_catalog_impact_manifest.py")
loader = load_module("catalog_impact_manifest", "utils/catalog_impact_manifest.py")


def test_manifest_round_trip_and_hash():
    audit = {"version": 5, "retire_ids": [100, 2, 50, 2, 999999]}
    manifest = builder.build_manifest(audit, snapshot="2026-09-05", source_pr=40)
    decoded = loader.decode_candidate_manifest(manifest)
    assert decoded == [2, 50, 100, 999999]
    assert manifest["candidate_count"] == 4
    assert manifest["candidate_ids_sha256"] == loader.candidate_ids_hash(decoded)
    assert manifest["policy"]["owner_review_threshold"] == 10
    assert manifest["policy"]["copy_review_threshold"] == 20


def test_manifest_rejects_empty_retire_list():
    try:
        builder.build_manifest({"version": 5, "retire_ids": []}, snapshot="2026-09-05")
    except ValueError as exc:
        assert "retire_ids" in str(exc)
    else:
        raise AssertionError("empty retirement list should fail")
