from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_profile_overview_route_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "profile_overview.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/api/menu/profile")' not in legacy
    assert "def _menu_user_payload(" not in legacy
    assert '@router.get("/api/menu/profile")' in route
    assert "build_profile_overview_router" in entrypoint
    assert "app.include_router(profile_overview_router)" in entrypoint


def test_profile_overview_route_keeps_signed_identity_and_dependencies() -> None:
    route = (ROOT / "webapp_routes" / "profile_overview.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in route
    assert "x_telegram_init_data=x_telegram_init_data" in route
    assert "x_webapp_uid=x_webapp_uid" in route
    assert "uid=uid" in route
    assert "collection_snapshot=collection_snapshot" in route
    assert "collection_cards_from_snapshot=collection_cards_from_snapshot" in route


def test_profile_overview_service_preserves_public_fields() -> None:
    service = (ROOT / "webapp_services" / "profile_overview.py").read_text(encoding="utf-8")

    for field in (
        '"user_id"',
        '"display_name"',
        '"username"',
        '"coins"',
        '"level"',
        '"collection_total"',
        '"nickname"',
        '"favorite"',
        '"country_code"',
        '"language"',
        '"private_profile"',
        '"notifications_enabled"',
    ):
        assert field in service

    assert '"countries": COUNTRY_OPTIONS' in service
    assert '"languages": LANGUAGE_OPTIONS' in service
    assert "image_url(character.get(\"image\"))" in service
