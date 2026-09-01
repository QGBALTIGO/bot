from __future__ import annotations

import ast
from pathlib import Path

import pytest

from premium_webapp_ui import (
    build_dado_page,
    build_home_page,
    build_media_catalog_page,
    build_menu_page,
    build_memory_page,
    build_shop_page,
)
from utils.aninexus_client import AniNexusClient, AniNexusError, _normalize_origin

ROOT = Path(__file__).resolve().parents[1]


def test_aninexus_origin_validation() -> None:
    assert _normalize_origin("https://aninexus.com.br/") == "https://aninexus.com.br"
    with pytest.raises(RuntimeError):
        _normalize_origin("javascript:alert(1)")
    with pytest.raises(RuntimeError):
        _normalize_origin("https://user:pass@aninexus.com.br")
    with pytest.raises(RuntimeError):
        _normalize_origin("https://aninexus.com.br/api")


def test_aninexus_client_rejects_arbitrary_proxy_paths() -> None:
    assert AniNexusClient._safe_path("/api/catalog") == "/api/catalog"
    assert AniNexusClient._safe_path("/api/anime/1") == "/api/anime/1"
    with pytest.raises(AniNexusError):
        AniNexusClient._safe_path("https://example.com/private")
    with pytest.raises(AniNexusError):
        AniNexusClient._safe_path("/api/admin/users")
    with pytest.raises(AniNexusError):
        AniNexusClient._safe_path("/api/catalog-admin")
    with pytest.raises(AniNexusError):
        AniNexusClient._safe_path("/health/private")


def test_webapp_registers_aninexus_router() -> None:
    source = (ROOT / "webapp.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "aninexus_router"
        for alias in node.names
    }
    assert "router" in imports
    assert "app.include_router(aninexus_router)" in source


def test_global_shell_uses_aninexus_identity() -> None:
    html = build_home_page(
        top_banner_url="https://example.com/top.jpg",
        catalog_banner_url="https://example.com/catalog.jpg",
        manga_banner_url="https://example.com/manga.jpg",
        cards_banner_url="https://example.com/cards.jpg",
        shop_banner_url="https://example.com/shop.jpg",
    )
    assert "AniNexus × Source Baltigo" in html
    assert "nx-topbar" in html
    assert "nx-bottom-nav" in html
    assert "/assets/logo.png" in html
    assert "/api/aninexus/home" in html
    assert "x-telegram-init-data" in html


def test_catalog_prefers_aninexus_with_local_fallback() -> None:
    html = build_media_catalog_page(
        page_title="Catálogo",
        hero_tag="Anime",
        hero_title="Animes",
        hero_copy="Teste",
        banner_url="https://example.com/banner.jpg",
        api_letters="/api/letters",
        api_catalog="/api/catalogo",
        search_placeholder="Buscar",
        footer_label="Catálogo",
        default_badge="Anime",
    )
    assert '"aninexusApi": "/api/aninexus/catalog"' in html
    assert '"localApiCatalog": "/api/catalogo"' in html
    assert "fetchAniNexus" in html
    assert "fetchLocal" in html


def test_profile_and_gacha_use_new_nexus_experience() -> None:
    profile = build_menu_page(uid=123, menu_banner_url="https://example.com/menu.jpg")
    gacha = build_dado_page(uid=123, banner_url="https://example.com/dado.jpg")
    assert "Nexus ID" in profile
    assert "nx-action-grid" in profile
    assert "/api/aninexus/home" in profile
    assert "Nexus Core" in gacha
    assert "emitNexusBurst" in gacha
    assert "THREE.MeshPhysicalMaterial" in gacha
    assert "x-telegram-init-data" in gacha


def test_shop_and_game_share_the_aninexus_shell() -> None:
    shop = build_shop_page(uid=123, shop_banner_url="https://example.com/shop.jpg")
    game = build_memory_page(uid=123, banner_url="https://example.com/game.jpg")
    for page in (shop, game):
        assert 'data-aninexus-miniapp="true"' in page
        assert "nx-topbar" in page
        assert "nx-bottom-nav" in page
        assert "https://aninexus.com.br/assets/logo.png" in page
        assert "x-telegram-init-data" in page
