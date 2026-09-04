from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_image_proxy_route_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "image_proxy.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/api/image-proxy")' not in legacy
    assert '@router.get("/api/image-proxy")' in module
    assert "from webapp_routes.image_proxy import router as image_proxy_router" in entrypoint
    assert "app.include_router(image_proxy_router)" in entrypoint


def test_image_proxy_contract_is_preserved() -> None:
    module = (ROOT / "webapp_routes" / "image_proxy.py").read_text(encoding="utf-8")

    assert 'Query(..., min_length=8, max_length=2000)' in module
    assert 'Query("", max_length=20)' in module
    assert '"X-Image-Crop": "2:3" if applied_crop else "original"' in module
    assert '"Cache-Control": "public, max-age=604800, stale-while-revalidate=86400"' in module


def test_channel_routes_live_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "channel.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/api/channel/selftest")' not in legacy
    assert '@app.post("/api/channel/check")' not in legacy
    assert '@router.get("/api/channel/selftest")' in module
    assert '@router.post("/api/channel/check")' in module
    assert "build_channel_router" in entrypoint
    assert "app.include_router(channel_router)" in entrypoint


def test_channel_route_contract_and_privacy_are_preserved() -> None:
    module = (ROOT / "webapp_routes" / "channel.py").read_text(encoding="utf-8")

    assert "timeout_seconds=8.0" in module
    assert "status_code=403" in module
    assert 'status_code=503 if status == "timeout" else 502' in module
    assert "require_internal_api_secret(x_internal_api_secret)" in module
    assert "resolve_webapp_user(" in module
    assert "user_id={user_id}" not in module


def test_webapp_context_route_lives_outside_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "context.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/api/webapp/context")' not in legacy
    assert '@router.get("/api/webapp/context")' in module
    assert "build_context_router" in entrypoint
    assert "app.include_router(context_router)" in entrypoint


def test_webapp_context_contract_is_preserved() -> None:
    module = (ROOT / "webapp_routes" / "context.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in module
    assert '"auth_mode": str(ctx.get("auth_mode") or "")' in module
    assert '"collection_total": len(cards)' in module
    assert '"xcollection_total": len(xcards)' in module
    assert '"xcollection_copies": sum(' in module
    assert "touch_user_identity(" in module


def test_simple_profile_setting_routes_live_outside_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "profile_settings.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    for path in (
        "/api/menu/nickname",
        "/api/menu/country",
        "/api/menu/language",
        "/api/menu/privacy",
        "/api/menu/notifications",
    ):
        assert f'@app.post("{path}")' not in legacy
        assert f'@router.post("{path}")' in module

    assert "profile_settings_router" in entrypoint
    assert "app.include_router(profile_settings_router)" in entrypoint


def test_simple_profile_setting_contract_is_preserved() -> None:
    module = (ROOT / "webapp_routes" / "profile_settings.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in module
    assert "language not in LANGUAGE_CODES" in module
    assert '"Idioma inválido."' in module
    assert '"Valor de privacidade inválido."' in module
    assert '"Valor de notificação inválido."' in module
    assert "set_profile_language(user_id, language)" in module
    assert 'set_profile_private(int(ctx["user_id"]), value)' in module
    assert 'set_profile_notifications(int(ctx["user_id"]), value)' in module


def test_profile_nickname_contract_is_preserved() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "profile_settings.py").read_text(encoding="utf-8")

    assert "def _valid_menu_nickname(" not in legacy
    assert 're.match(r"^[A-Z][A-Za-z0-9_]{3,16}$", nickname)' in module
    assert '"Nickname inválido. Use 4-17 caracteres, começando com letra maiúscula."' in module
    assert 'error == "nickname_locked"' in module
    assert '"Você já definiu seu nickname."' in module
    assert 'error == "nickname_taken"' in module
    assert '"Esse nickname já está em uso."' in module
    assert "status_code=409" in module
    assert "set_profile_nickname(user_id, nickname)" in module


def test_profile_country_contract_is_preserved() -> None:
    module = (ROOT / "webapp_routes" / "profile_settings.py").read_text(encoding="utf-8")
    options = (ROOT / "utils" / "profile_options.py").read_text(encoding="utf-8")
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")

    assert "country_code not in COUNTRY_CODES" in module
    assert '"País inválido."' in module
    assert "set_profile_country(user_id, country_code)" in module
    assert '{"code": "BR", "flag": "🇧🇷", "name": "Brasil"}' in options
    assert '{"code": "US", "flag": "🇺🇸", "name": "United States"}' in options
    assert '{"code": "ES", "flag": "🇪🇸", "name": "España"}' in options
    assert '{"code": "JP", "flag": "🇯🇵", "name": "日本"}' in options
    assert "COUNTRY_CODES = frozenset" in options
    assert "LANGUAGE_CODES = frozenset" in options
    assert "COUNTRY_OPTIONS = [" not in legacy
    assert "LANGUAGE_OPTIONS = [" not in legacy
    assert "from utils.profile_options import COUNTRY_OPTIONS, LANGUAGE_OPTIONS" in legacy


def test_profile_collection_and_favorite_routes_live_outside_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "profile_collection.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/api/menu/collection-characters")' not in legacy
    assert '@app.post("/api/menu/favorite")' not in legacy
    assert '@router.get("/api/menu/collection-characters")' in module
    assert '@router.post("/api/menu/favorite")' in module
    assert "profile_collection_router" in entrypoint
    assert "app.include_router(profile_collection_router)" in entrypoint


def test_profile_favorite_ownership_contract_is_preserved() -> None:
    module = (ROOT / "webapp_routes" / "profile_collection.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in module
    assert '"Personagem inválido."' in module
    assert "status_code=400" in module
    assert "owned_ids = {" in module
    assert '"Você só pode favoritar personagens da sua coleção."' in module
    assert "status_code=403" in module
    assert "set_profile_favorite(user_id, character_id)" in module


def test_profile_collection_service_replaces_legacy_helper() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    service = (ROOT / "webapp_services" / "profile_collection.py").read_text(encoding="utf-8")

    assert "def _menu_collection_characters(" not in legacy
    assert "menu_collection_characters as _menu_collection_characters" in legacy
    assert "def menu_collection_characters(" in service
    assert '(item["anime"] or "").lower()' in service
    assert '(item["name"] or "").lower()' in service
    assert '"quantity": qty' in service


def test_web_image_url_replaces_legacy_helper() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    utility = (ROOT / "utils" / "web_image_url.py").read_text(encoding="utf-8")

    assert "def _web_image_url(" not in legacy
    assert "web_image_url as _web_image_url" in legacy
    assert "DIRECT_IMAGE_HOSTS = {" not in legacy
    assert "def web_image_url(" in utility
    assert '"s4.anilist.co"' in utility
    assert '"img.anili.st"' in utility
    assert 'host == "w.wallhaven.cc"' in utility
    assert '"/api/image-proxy?crop=portrait&url=' in utility
