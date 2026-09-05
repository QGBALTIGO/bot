from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dado_catalog_runtime",
    ROOT / "utils" / "dado_catalog_runtime.py",
)
dado_catalog = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(dado_catalog)


def base_assets():
    return {
        "items": [
            {
                "anime_id": 1,
                "anime": "Old Anime",
                "banner_image": "banner-1",
                "cover_image": "cover-1",
                "characters": [
                    {"id": 10, "name": "Keep Me", "image": "old-10"},
                    {"id": 11, "name": "Retire Me", "image": "old-11"},
                ],
            }
        ]
    }


def overrides():
    return {
        "deleted_characters": [11],
        "deleted_animes": [],
        "custom_animes": [
            {"anime_id": 20, "anime": "Naruto", "banner_image": "naruto-banner"},
        ],
        "custom_characters": [
            {"id": 17, "anime_id": 20, "anime": "Naruto", "name": "Naruto Uzumaki", "image": "naruto-old"},
        ],
        "character_name_overrides": {"10": "Keep Me Renamed"},
        "character_image_overrides": {"10": "better-10", "17": "better-naruto"},
        "anime_name_overrides": {},
        "anime_banner_overrides": {},
        "anime_cover_overrides": {},
    }


def test_dado_pool_applies_deletions_additions_and_overrides():
    payload = dado_catalog.build_dado_catalog(base_assets(), overrides())
    items = payload["items"]
    all_chars = [ch for anime in items for ch in anime["characters"]]
    by_id = {int(ch["id"]): ch for ch in all_chars}
    anime_ids = {int(anime["anime_id"]) for anime in items}

    assert 11 not in by_id
    assert by_id[10]["name"] == "Keep Me Renamed"
    assert by_id[10]["image"] == "better-10"
    assert by_id[17]["name"] == "Naruto Uzumaki"
    assert by_id[17]["image"] == "better-naruto"
    assert 20 in anime_ids
    assert payload["summary"]["deleted_characters_applied"] == 1


def test_deleted_anime_never_enters_dado_pool():
    data = overrides()
    data["deleted_animes"] = [1]
    payload = dado_catalog.build_dado_catalog(base_assets(), data)
    assert all(int(anime["anime_id"]) != 1 for anime in payload["items"])


def test_same_character_id_is_not_rolled_twice_across_sequels():
    assets = {
        "items": [
            {"anime_id": 1, "anime": "A", "characters": [{"id": 50, "name": "Shared"}]},
            {"anime_id": 2, "anime": "B", "characters": [{"id": 50, "name": "Shared"}]},
        ]
    }
    payload = dado_catalog.build_dado_catalog(assets, {})
    ids = [int(ch["id"]) for anime in payload["items"] for ch in anime["characters"]]
    assert ids.count(50) == 1


def test_configure_writes_materialized_pool_and_sets_environment(tmp_path: Path, monkeypatch):
    assets_path = tmp_path / "assets.json"
    overrides_path = tmp_path / "overrides.json"
    output_path = tmp_path / "dado-final.json"
    assets_path.write_text(json.dumps(base_assets()), encoding="utf-8")
    overrides_path.write_text(json.dumps(overrides()), encoding="utf-8")
    monkeypatch.delenv("CARDS_LOCAL_PATH", raising=False)

    stats = dado_catalog.configure_dado_catalog_pool(
        assets_path=assets_path,
        overrides_path=overrides_path,
        output_path=output_path,
    )

    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "source.dado-catalog.materialized.v1"
    assert os.environ["CARDS_LOCAL_PATH"] == str(output_path)
    assert stats["characters"] == 2


def test_standalone_webapp_materializes_dado_pool_before_importing_legacy_webapp():
    text = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")
    bootstrap = text.index("_DADO_CATALOG_BOOTSTRAP = configure_dado_catalog_pool()")
    legacy_import = text.index("from webapp import")
    assert bootstrap < legacy_import


def test_full_bot_imports_dado_bootstrap_before_webapp_is_started():
    bot = (ROOT / "bot.py").read_text(encoding="utf-8")
    dado_import = bot.index("from commands.dado import dado")
    webapp_start = bot.index("def run_webapp")
    assert dado_import < webapp_start

    command = (ROOT / "commands" / "dado.py").read_text(encoding="utf-8")
    assert "_DADO_CATALOG_BOOTSTRAP = configure_dado_catalog_pool()" in command
