from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Contract between Telegram buttons and HTTP pages. A button may only target a
# page that is actually registered by the legacy monolith or a V2 route module.
PAGE_CONTRACTS = {
    "/hub": "hub_webapp.py",
    "/agenda": "agenda_webapp.py",
    "/game": "game_webapp.py",
    "/collection": "collection_webapp.py",
    "/profile": "profile_webapp.py",
    "/ranking": "ranking_webapp.py",
    "/shop-v2": "shop_webapp.py",
    "/xcards": "xcards_webapp.py",
    "/xcollection": "xcards_webapp.py",
    "/memory": "memory_webapp_v2.py",
    "/termo": "termo_webapp_v2.py",
    "/messages": "messages_webapp.py",
    "/contribute": "contrib_webapp.py",
    "/catalogo": "webapp.py",
    "/mangas": "webapp.py",
    "/cards": "webapp.py",
    "/pedido": "webapp.py",
    "/baltigoflix": "webapp.py",
    "/terms": "webapp.py",
}


def _declares_get_route(text: str, path: str) -> bool:
    return (
        f'@app.get("{path}"' in text
        or f"@app.get('{path}'" in text
    )


def test_every_button_destination_has_http_page():
    missing = []
    for path, module in PAGE_CONTRACTS.items():
        text = (ROOT / module).read_text(encoding="utf-8")
        if not _declares_get_route(text, path):
            missing.append(f"{path} -> {module}")
    assert not missing, "Páginas ausentes para destinos de WebApp: " + ", ".join(missing)


def test_v2_registry_registers_all_v2_page_modules():
    registry = (ROOT / "v2_webapp_registry.py").read_text(encoding="utf-8")
    required_registration_calls = {
        "register_health_routes(app)",
        "register_game_routes(app)",
        "register_collection_routes(app)",
        "register_profile_routes(app)",
        "register_ranking_routes(app)",
        "register_shop_routes(app)",
        "register_xcards_routes(app)",
        "register_memory_routes(app)",
        "register_termo_routes(app)",
        "register_message_routes(app)",
        "register_contribution_routes(app)",
        "register_hub_routes(app)",
        "register_agenda_routes(app)",
    }
    missing = sorted(call for call in required_registration_calls if call not in registry)
    assert not missing, "Registradores V2 ausentes: " + ", ".join(missing)


def test_main_webapp_entries_use_signed_builder_or_shared_v2_entry():
    files = [
        "commands/start.py",
        "commands/anime.py",
        "commands/manga.py",
        "commands/cards.py",
        "commands/pedido.py",
        "commands/baltigoflix.py",
        "commands/v2_entry.py",
    ]
    missing = []
    for relative in files:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if "build_webapp_url" not in text:
            missing.append(relative)
    assert not missing, "Entradas WebApp sem URL assinada: " + ", ".join(missing)
