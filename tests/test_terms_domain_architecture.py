from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_terms_domain_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "terms.py").read_text(encoding="utf-8")
    service = (ROOT / "webapp_services" / "terms.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert "def pick_lang(" not in legacy
    assert "TEXTS = {" not in legacy
    assert "TERMS_LONG = {" not in legacy
    assert 'TERMS_HTML = """' not in legacy

    for path, method in (
        ("/terms", "get"),
        ("/api/terms/accept", "post"),
        ("/api/terms/decline", "post"),
    ):
        assert f'@app.{method}("{path}"' not in legacy
        assert f'@router.{method}("{path}"' in route

    assert "from webapp_services.terms import TERMS_VERSION" in legacy
    assert "TERMS_VERSION =" in service
    assert "def pick_lang(" in service
    assert "TEXTS = {" in service
    assert "TERMS_LONG = {" in service
    assert 'TERMS_HTML = """' in service

    assert "from webapp_routes.terms import build_terms_router" in entrypoint
    assert "app.include_router(terms_router)" in entrypoint


def test_terms_routes_keep_signed_identity_and_database_contract() -> None:
    route = (ROOT / "webapp_routes" / "terms.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in route
    assert route.count("_resolve_webapp_user(") == 2
    assert 'body_uid=payload.get("uid")' in route
    assert "from database import accept_terms, create_or_get_user, set_language" in route
    assert "from database import create_or_get_user, set_language" in route
    assert "accept_terms(user_id, TERMS_VERSION)" in route
    assert "set_language(user_id, language)" in route
    assert 'except HTTPException:' in route
    assert 'status_code=500' in route


def test_terms_page_keeps_current_configuration_inputs() -> None:
    route = (ROOT / "webapp_routes" / "terms.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert "required_channel_url=REQUIRED_CHANNEL_URL" in entrypoint
    assert "top_banner_url=TOP_BANNER_URL" in entrypoint
    assert "background_url=BACKGROUND_URL" in entrypoint
    assert "empty_bg_data_uri=EMPTY_BG_DATA_URI" in entrypoint

    assert 'href="{required_channel_url}"' in route
    assert '.replace("__TVERSION__", TERMS_VERSION.upper())' in route
    assert '.replace("__TOPBANNER__", top_banner_url)' in route
    assert '.replace("__BGURL__", bg)' in route


def test_terms_db_helpers_are_not_left_imported_by_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")

    assert "    accept_terms,\n" not in legacy
    assert "    set_language,\n" not in legacy
