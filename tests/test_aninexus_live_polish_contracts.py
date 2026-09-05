from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pet_json_metadata_parameters_are_explicitly_typed():
    source = _read("database_aninexus_pets.py")
    assert "jsonb_build_object('pet_id', %s::text)" in source
    assert "jsonb_build_object('pet_id',%s)" not in source
    assert "jsonb_build_object('pet_id', %s)" not in source


def test_dado_roll_quest_handles_legacy_unix_timestamp():
    source = _read("database_aninexus_progression_source.py")
    assert "FROM dice_rolls" in source
    assert "to_timestamp(" in source
    assert "created_at::double precision" in source


def test_dado_reward_returns_to_private_chat_once():
    source = _read("webapp_routes/aninexus_dado.py")
    assert "def _deliver_dado_reward(" in source
    assert 'dedupe_key=f"dado:{int(user_id)}:{int(roll_id)}"' in source
    assert "if not already_done:" in source
    assert "_deliver_dado_reward(" in source
    assert '"tier": tier["tier"]' in source
    assert '"stars": tier["stars"]' in source
    assert "Adicionado à sua coleção!" in source


def test_portuguese_translator_does_not_replace_substrings_inside_words():
    source = _read("aninexus_frontend/src/ptBR.ts")
    assert "EXACT[core]" in source
    assert "out.includes(from)" not in source
    assert "out.split(from).join(to)" not in source
    assert "'Rankings': 'Ranking'" in source
    assert "'INTERNAL SERVER ERROR': 'ERRO INTERNO NO SERVIDOR'" in source


def test_api_errors_are_localized_for_visible_failures():
    source = _read("aninexus_frontend/src/api/client.ts")
    assert "500: 'Erro interno no servidor.'" in source
    assert "Sessão expirada. Reabra a MiniApp." in source
    assert "Algo deu errado. Tente novamente." in source


def test_leaderboard_uses_http_polling_in_current_runtime():
    source = _read("aninexus_frontend/src/pages/Leaderboard.tsx")
    assert "new WebSocket" not in source
    assert "window.setInterval" in source
    assert "30000" in source
    assert ">Ranking</h1>" in source


def test_profile_known_visible_copy_is_native_portuguese():
    source = _read("aninexus_frontend/src/pages/Profile.tsx")
    for forbidden in (
        "Your collection",
        "Every waifu you've collected",
        "ALL RARITIES",
        "Search characters...",
        "Nothing here yet",
        "Hatch some eggs to start your collection.",
        "COMPANION",
        "INCUBATOR",
        "COMBAT RECORD",
    ):
        assert forbidden not in source
    assert "Sua coleção" in source
    assert "TODAS AS RARIDADES" in source


def test_hatchery_primary_actions_are_native_portuguese():
    source = _read("aninexus_frontend/src/pages/Hatchery.tsx")
    for forbidden in (
        "Incubation started.",
        "Egg sold.",
        "Egg purified.",
        "Eggs fused.",
        ">Hatchery</h1>",
        "m remaining",
    ):
        assert forbidden not in source
    assert "Incubação iniciada." in source
    assert ">Incubadora</h1>" in source
    assert "min restantes" in source


def test_trade_cards_have_explicit_ratio_and_wait_for_target_collection():
    source = _read("aninexus_frontend/src/pages/Trading.tsx")
    assert "style={{ aspectRatio: '2 / 3' }}" in source
    assert "targetChars.length > 0 && (myLoading || myChars.length > 0)" in source


def test_global_rarity_labels_are_localized():
    source = _read("aninexus_frontend/src/utils/index.ts")
    assert "common: 'Comum'" in source
    assert "uncommon: 'Incomum'" in source
    assert "legendary: 'Lendário'" in source
    assert "SEM IMAGEM" in source
