from __future__ import annotations

from premium_webapp_ui import (
    build_cards_home_page,
    build_media_catalog_page,
    build_request_center_page,
    build_shop_page,
)
from webapp_services.terms import TERMS_HTML


def _assert_aninexus_shell(html: str) -> None:
    assert 'class="nx-app-header"' in html
    assert 'id="nxMenuButton"' in html
    assert 'id="nxDrawer"' in html
    assert 'href="/shop"' in html
    assert 'href="/catalogo"' in html
    assert 'href="/pedido"' in html
    assert 'content="#09090b"' in html
    assert "--accent:#3b82f6" in html
    assert html.rindex("--accent:#3b82f6") > html.rindex("--accent:#ff6f94")
    assert "setupAppChrome();" in html


def test_catalog_shop_requests_and_cards_share_aninexus_shell() -> None:
    pages = [
        build_media_catalog_page(
            page_title="Animes",
            hero_tag="Catálogo",
            hero_title="Animes",
            hero_copy="Catálogo de animes",
            banner_url="https://example.com/animes.jpg",
            api_letters="/api/letters",
            api_catalog="/api/catalogo",
            search_placeholder="Buscar anime",
            footer_label="AniNexus",
            default_badge="Anime",
        ),
        build_shop_page(uid=123, shop_banner_url="https://example.com/shop.jpg"),
        build_request_center_page(uid=123, banner_url="https://example.com/request.jpg"),
        build_cards_home_page(top_banner_url="https://example.com/cards.jpg"),
    ]

    for page in pages:
        _assert_aninexus_shell(page)


def test_shared_navigation_preserves_user_context_and_marks_routes() -> None:
    html = build_shop_page(uid=123, shop_banner_url="https://example.com/shop.jpg")

    assert "data-preserve-uid" in html
    assert 'data-routes="/shop,/loja"' in html
    assert 'target.searchParams.set("uid", String(uid));' in html
    assert 'link.setAttribute("aria-current", "page")' in html


def test_terms_onboarding_uses_the_same_aninexus_foundation() -> None:
    assert 'content="#09090b"' in TERMS_HTML
    assert 'family=JetBrains+Mono' in TERMS_HTML
    assert "--accent:#3b82f6" in TERMS_HTML
    assert 'background: #0c0c0e;' in TERMS_HTML
    assert 'tg.setHeaderColor("#09090b")' in TERMS_HTML
