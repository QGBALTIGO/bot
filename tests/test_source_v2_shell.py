from __future__ import annotations

from webapp_routes.source_v2 import build_source_v2_router


def _page_html() -> str:
    router = build_source_v2_router(banner_url="https://example.com/banner.jpg")
    route = next(route for route in router.routes if route.path == "/source-v2")
    response = route.endpoint(uid=123)
    return response.body.decode("utf-8")


def test_source_v2_exposes_primary_and_alias_routes() -> None:
    router = build_source_v2_router(banner_url="https://example.com/banner.jpg")
    paths = {route.path for route in router.routes}
    assert "/source-v2" in paths
    assert "/app-v2" in paths


def test_source_v2_uses_seal_style_font_stack_and_telegram_sdk() -> None:
    html = _page_html()
    assert "family=Outfit" in html
    assert "JetBrains+Mono" in html
    assert "https://telegram.org/js/telegram-web-app.js" in html


def test_source_v2_cards_are_standardized_to_two_by_three() -> None:
    html = _page_html()
    assert "aspect-ratio:2/3" in html


def test_source_v2_preserves_signed_webapp_auth() -> None:
    html = _page_html()
    assert "x-telegram-init-data" in html
    assert "x-webapp-uid" in html
    assert "/api/menu/profile" in html
    assert "/api/collection/state" in html
    assert "/api/collection/cards" in html


def test_source_v2_contains_native_telegram_experience_hooks() -> None:
    html = _page_html()
    assert "HapticFeedback" in html
    assert "BackButton" in html
    assert "themeChanged" in html
    assert "disableVerticalSwipes" in html
    assert "enableVerticalSwipes" in html


def test_source_v2_contains_visible_seal_attribution() -> None:
    html = _page_html()
    assert "AniNexus" in html
    assert "bisug" in html
