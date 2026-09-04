from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_domain_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "catalog.py").read_text(encoding="utf-8")
    service = (ROOT / "webapp_services" / "catalog.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    legacy_functions = (
        "_normalize_title",
        "_first_letter",
        "_safe_int",
        "_coerce_item",
        "_load_catalog",
        "_filter_catalog",
        "_detect_manga_badge",
        "_coerce_manga_item",
        "_load_manga_catalog",
        "_filter_manga_catalog",
    )
    for name in legacy_functions:
        assert f"def {name}(" not in legacy

    for path, method in (
        ("/api/letters", "get"),
        ("/api/catalogo", "get"),
        ("/catalogo", "get"),
        ("/api/mangas/letters", "get"),
        ("/api/mangas/catalogo", "get"),
        ("/mangas", "get"),
    ):
        assert f'@app.{method}("{path}"' not in legacy
        assert f'@router.{method}("{path}"' in route

    assert "from webapp_routes.catalog import router as catalog_router" in entrypoint
    assert "app.include_router(catalog_router)" in entrypoint
    assert "def _load_catalog(" in service
    assert "def _load_manga_catalog(" in service


def test_shared_record_parser_moves_without_breaking_pedido() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    utility = (ROOT / "utils" / "catalog_records.py").read_text(encoding="utf-8")

    assert "def _unwrap_records(" not in legacy
    assert "from utils.catalog_records import unwrap_records as _unwrap_records" in legacy
    assert "def unwrap_records(" in utility
    assert "def _pedido_reload_indexes(" in legacy
    assert "_unwrap_records(anime_payload)" in legacy
    assert "_unwrap_records(manga_payload)" in legacy
    assert "def _pedido_catalog_contains(" in legacy


def test_home_keeps_catalog_banner_compatibility_reexports() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    service = (ROOT / "webapp_services" / "catalog.py").read_text(encoding="utf-8")

    assert (
        "from webapp_services.catalog import CATALOG_BANNER_URL, MANGA_CATALOG_BANNER_URL"
        in legacy
    )
    assert "catalog_banner_url=CATALOG_BANNER_URL" in legacy
    assert "manga_banner_url=MANGA_CATALOG_BANNER_URL" in legacy
    assert "CATALOG_BANNER_URL =" in service
    assert "MANGA_CATALOG_BANNER_URL =" in service


def test_catalog_page_builder_moves_out_of_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "catalog.py").read_text(encoding="utf-8")

    assert "build_media_catalog_page as build_media_catalog_page_html" not in legacy
    assert "build_media_catalog_page as build_media_catalog_page_html" in route
    assert 'api_letters="/api/letters"' in route
    assert 'api_catalog="/api/catalogo"' in route
    assert 'api_letters="/api/mangas/letters"' in route
    assert 'api_catalog="/api/mangas/catalogo"' in route


def test_catalog_startup_loading_is_preserved_in_service() -> None:
    service = (ROOT / "webapp_services" / "catalog.py").read_text(encoding="utf-8")

    assert "_load_catalog()" in service
    assert "_load_manga_catalog()" in service
    assert 'print("[catalog] ERRO inesperado no startup:"' in service
    assert 'print("[mangas] ERRO inesperado no startup:"' in service
    assert "def catalog_letters_payload(" in service
    assert "def manga_letters_payload(" in service
    assert "def filter_catalog(" in service
    assert "def filter_manga_catalog(" in service
