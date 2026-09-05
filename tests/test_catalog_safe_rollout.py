from __future__ import annotations

from utils.catalog_safe_rollout import load_safe_additions, merge_safe_additions


def test_real_safe_rollout_manifest_is_complete_and_curated():
    safe = load_safe_additions()
    assert safe["character_count"] == 493
    assert {int(row["anime_id"]) for row in safe["custom_animes"]} == {20, 147105}

    ids = {int(row["id"]) for row in safe["custom_characters"]}
    assert {17, 13, 85, 53901, 129840, 129841}.issubset(ids)

    # Exemplos do ruído detectado no lote bruto; não podem voltar ao catálogo.
    assert 302593 not in ids  # Biyooshi / default image / 1 favorito
    assert 302594 not in ids  # Esthetician / default image / 1 favorito
    assert 368004 not in ids  # Marina no Yuujin / personagem genérico


def test_manual_overrides_and_deletions_keep_priority_over_safe_rollout():
    safe = load_safe_additions()
    base = {
        "deleted_characters": [17],
        "deleted_animes": [147105],
        "custom_animes": [{"anime_id": 20, "anime": "Naruto Manual"}],
        "custom_characters": [
            {"id": 17, "anime_id": 20, "name": "Naruto Manual", "image": "https://example.com/naruto.jpg"}
        ],
        "character_image_overrides": {},
        "character_name_overrides": {"3149": "Obito Manual"},
        "anime_name_overrides": {},
        "anime_banner_overrides": {},
        "anime_cover_overrides": {},
        "subcategories": {},
    }

    merged = merge_safe_additions(base, safe)
    assert merged["deleted_characters"] == [17]
    assert merged["deleted_animes"] == [147105]
    assert next(row for row in merged["custom_animes"] if int(row["anime_id"]) == 20)["anime"] == "Naruto Manual"
    assert sum(1 for row in merged["custom_characters"] if int(row["id"]) == 17) == 1
    assert merged["character_name_overrides"]["3149"] == "Obito Manual"
    assert merged["_safe_catalog_rollout"]["retirements_applied"] == 0
    assert merged["_safe_catalog_rollout"]["coins_awarded"] == 0
