from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dado_delivers_directly_before_outbox_fallback():
    source = _read("webapp_routes/aninexus_dado.py")
    function = source[source.index("def _deliver_dado_reward"):source.index("def build_aninexus_dado_router")]
    assert "sendPhoto" in function
    assert "sendMessage" in function
    assert "response.raise_for_status()" in source
    assert function.index("_telegram_bot_call") < function.index("enqueue_photo")
    assert "tier[\"tier\"]" in source


def test_high_traffic_ui_has_native_portuguese_copy():
    files = {
        "gallery": _read("aninexus_frontend/src/pages/Gallery.tsx"),
        "pet_modal": _read("aninexus_frontend/src/components/pet/PetActionModal.tsx"),
        "character_modal": _read("aninexus_frontend/src/components/character/Modal.tsx"),
        "actions": _read("aninexus_frontend/src/components/character/CharActionModal.tsx"),
        "reward": _read("aninexus_frontend/src/components/minigames/RewardModal.tsx"),
        "memory": _read("aninexus_frontend/src/components/minigames/CipherMatch.tsx"),
        "intro": _read("aninexus_frontend/src/components/IntroLoading.tsx"),
        "error": _read("aninexus_frontend/src/components/ui/ErrorState.tsx"),
        "empty": _read("aninexus_frontend/src/components/ui/EmptyState.tsx"),
    }
    forbidden = (
        "Archive Mismatch",
        "ALL RARITIES",
        "Mystery Prize",
        "Confirm & Close",
        "Active Sync",
        "Activate Companion",
        "Visit Breeder",
        "Grid Sync",
        "Sync Capacity",
        "Connection failed",
        "Waifu Collector",
        "Signed in via Telegram",
        "End of Data",
    )
    joined = "\n".join(files.values())
    for phrase in forbidden:
        assert phrase not in joined


def test_rarity_labels_are_portuguese_in_shared_surfaces():
    utils = _read("aninexus_frontend/src/utils/index.ts")
    modal = _read("aninexus_frontend/src/components/character/Modal.tsx")
    gacha = _read("aninexus_frontend/src/components/ui/GachaReveal.tsx")
    reward = _read("aninexus_frontend/src/components/minigames/RewardModal.tsx")
    assert "common: 'Comum'" in utils
    assert "legendary: 'Lendário'" in utils
    assert "cleanRarityLabel(character.rarity)" in modal
    assert "cleanRarityLabel(character.rarity)" in gacha
    assert "cleanRarityLabel(rewards.character.rarity)" in reward


def test_live_regressions_from_reported_errors_stay_fixed():
    pets = _read("database_aninexus_pets.py")
    progression = _read("database_aninexus_progression_source.py")
    client = _read("aninexus_frontend/src/api/client.ts")
    ptbr = _read("aninexus_frontend/src/ptBR.ts")
    assert "jsonb_build_object('pet_id', %s::text)" in pets
    assert "to_timestamp(" in progression
    assert "500: 'Erro interno no servidor.'" in client
    assert "EXACT[core] ?? core" in ptbr
