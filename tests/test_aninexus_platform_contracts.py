from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dado_command_opens_aninexus_module():
    source = _read("commands/dado.py")
    assert '/menu?tab=dado&uid=' in source
    assert 'WebAppInfo(url=url)' in source


def test_aninexus_runtime_is_the_menu_entrypoint():
    source = _read("webapp_entrypoint.py")
    assert "install_aninexus_runtime(app)" in source
    assert "build_aninexus_me_router" in source
    assert "build_aninexus_games_router" in source
    assert "build_aninexus_dado_router" in source
    assert "build_aninexus_shop_router" in source
    assert "build_aninexus_social_router" in source
    assert "build_aninexus_pets_router" in source


def test_real_aninexus_routers_are_registered_before_compatibility_fallback():
    source = _read("webapp_entrypoint.py")
    compat_position = source.index("app.include_router(aninexus_compat_router)")
    for marker in (
        "app.include_router(aninexus_me_router)",
        "app.include_router(aninexus_dado_router)",
        "app.include_router(aninexus_games_router)",
        "app.include_router(aninexus_ranking_router)",
        "app.include_router(aninexus_shop_router)",
        "app.include_router(aninexus_social_router)",
        "app.include_router(aninexus_pets_router)",
        "app.include_router(aninexus_progression_router)",
    ):
        assert source.index(marker) < compat_position


def test_games_use_server_side_pet_modifiers_and_source_rewards():
    source = _read("database_aninexus_games.py")
    assert "active_pet_modifiers" in source
    assert "xp_multiplier" in source
    assert "bonus_coin_chance" in source
    assert "energy_bonus" in source
    assert "egg_drop_chance" in source
    assert "aninexus_game_reward" in source
    assert "user_card_collection" in source
    assert "user_progress" in source


def test_source_identity_and_economy_remain_canonical():
    me_source = _read("webapp_routes/aninexus_me.py")
    shop_source = _read("webapp_routes/aninexus_shop.py")
    progression_source = _read("webapp_routes/aninexus_progression.py")

    assert "get_dado_state" in me_source
    assert "users.coins" in shop_source or "SELECT coins" in shop_source
    assert "database_aninexus_progression_source" in progression_source
    assert not (ROOT / "database_aninexus_progression.py").exists()
    assert not (ROOT / "aninexus_progression.py").exists()


def test_active_product_runtime_has_no_seal_named_modules():
    assert not (ROOT / "seal_frontend").exists()
    assert not (ROOT / "seal_runtime").exists()
    assert not (ROOT / "webapp_routes" / "seal_runtime.py").exists()
    assert not (ROOT / "webapp_routes" / "seal_compat.py").exists()


def test_companion_and_social_state_are_persistent():
    pets = _read("database_aninexus_pets.py")
    social = _read("database_aninexus_social.py")

    assert "aninexus_user_pets" in pets
    assert "aninexus_user_eggs" in pets
    assert "ON DELETE CASCADE" in pets
    assert "aninexus_referral_rewards" in social
    assert "FOR UPDATE" in social
    assert "card_trades" in social


def test_frontend_is_portuguese_aninexus_product():
    index = _read("aninexus_frontend/index.html")
    translations = _read("aninexus_frontend/src/ptBR.ts")
    drawer = _read("aninexus_frontend/src/components/NavigationDrawer.tsx")

    assert 'lang="pt-BR"' in index
    assert "<title>AniNexus</title>" in index
    assert "Jogos AniNexus" in translations
    assert "Loja de Companheiros" in drawer
    assert "SEAL YOUR WAIFU" not in index
