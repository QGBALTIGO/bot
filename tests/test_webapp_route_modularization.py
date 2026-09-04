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
    assert 'language not in {"pt", "en", "es"}' in module
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
