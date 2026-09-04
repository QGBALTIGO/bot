from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_menu_page_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "profile_page.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/menu", response_class=HTMLResponse)' not in legacy
    assert '@router.get("/menu", response_class=HTMLResponse)' in route
    assert "build_profile_page_router" in entrypoint
    assert "app.include_router(profile_page_router)" in entrypoint


def test_legacy_menu_html_and_unused_background_are_removed() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")

    assert "MENU_HTML =" not in legacy
    assert "MENU_BACKGROUND_URL =" not in legacy
    assert "MENU_BANNER_URL =" not in legacy
    assert 'id="deleteBtn"' not in legacy
    assert 'id="nicknameInput"' not in legacy


def test_profile_page_preserves_banner_and_render_contract() -> None:
    route = (ROOT / "webapp_routes" / "profile_page.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert 'os.getenv("MENU_BANNER_URL", default_banner_url).strip()' in route
    assert "build_menu_page as build_menu_page_html" in route
    assert "uid: int = Query(...)" in route
    assert "uid=int(uid)" in route
    assert "menu_banner_url=menu_banner_url" in route
    assert "default_banner_url=TOP_BANNER_URL" in entrypoint
