from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_collection_domain_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "collection.py").read_text(encoding="utf-8")
    service = (ROOT / "webapp_services" / "collection.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    legacy_functions = (
        "_collection_character_subcategory_map",
        "_collection_snapshot",
        "_collection_profile_payload",
        "_collection_cards_from_snapshot",
        "_collection_animes_from_snapshot",
        "_collection_detail_from_snapshot",
    )
    for name in legacy_functions:
        assert f"def {name}(" not in legacy

    for path in (
        "/api/collection/state",
        "/api/collection/cards",
        "/api/collection/animes",
        "/api/collection/anime",
    ):
        assert f'@app.get("{path}")' not in legacy
        assert f'@router.get("{path}")' in route

    assert '@app.get("/cccolecao", response_class=HTMLResponse)' not in legacy
    assert '@router.get("/cccolecao", response_class=HTMLResponse)' in route

    assert "def collection_snapshot(" in service
    assert "def collection_cards_from_snapshot(" in service
    assert "def collection_animes_from_snapshot(" in service
    assert "def collection_detail_from_snapshot(" in service
    assert "def collection_profile_payload(" in service

    assert "from webapp_services.collection import (" in entrypoint
    assert "collection_snapshot," in entrypoint
    assert "collection_cards_from_snapshot," in entrypoint
    assert "_collection_snapshot" not in entrypoint
    assert "_collection_cards_from_snapshot" not in entrypoint
    assert "app.include_router(collection_router)" in entrypoint


def test_collection_routes_keep_signed_identity_and_touch() -> None:
    route = (ROOT / "webapp_routes" / "collection.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in route
    assert "def _touch_identity(" in route
    assert "touch_user_identity(" in route
    assert route.count("_resolve_webapp_user(") == 4
    assert route.count("_touch_identity(user_id, ctx)") == 4
    assert 'anime_id: int = Query(..., ge=1)' in route
    assert 'mode: str = Query(default="owned")' in route
    assert '"Obra nao encontrada."' in route
    assert "status_code=404" in route


def test_collection_page_keeps_current_premium_builder_and_banner() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "collection.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert "build_collection_page as build_collection_page_html" not in legacy
    assert "build_collection_page as build_collection_page_html" in route
    assert "uid=int(uid or 0)" in route
    assert "banner_url=banner_url" in route
    assert "banner_url=CARDS_TOP_BANNER_URL" in entrypoint


def test_collection_service_reuses_shared_profile_and_image_services() -> None:
    service = (ROOT / "webapp_services" / "collection.py").read_text(encoding="utf-8")

    assert "from utils.web_image_url import web_image_url" in service
    assert "from webapp_services.profile_overview import build_menu_user_payload" in service
    assert "collection_snapshot=collection_snapshot" in service
    assert "collection_cards_from_snapshot=collection_cards_from_snapshot" in service
    assert 'mode_key not in {"owned", "missing", "gallery"}' in service
