from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_memory_domain_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "memory.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    for path, method in (
        ("/memoria", "get"),
        ("/memory", "get"),
        ("/api/memory/best", "get"),
        ("/api/memory/finish", "post"),
    ):
        assert f'@app.{method}("{path}"' not in legacy
        assert f'@router.{method}("{path}"' in route

    for name in ("memory_page", "memory_alias", "api_memory_best", "api_memory_finish"):
        assert f"def {name}(" not in legacy

    assert "from webapp_routes.memory import build_memory_router" in entrypoint
    assert "app.include_router(memory_router)" in entrypoint


def test_memory_routes_keep_signed_identity_and_touch() -> None:
    route = (ROOT / "webapp_routes" / "memory.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in route
    assert route.count("_resolve_webapp_user(") == 2
    assert route.count("_touch_identity(user_id, ctx)") == 2
    assert "touch_user_identity(" in route
    assert 'uid=payload.get("uid")' in route
    assert 'body_uid=payload.get("uid")' in route


def test_memory_contract_and_page_builder_are_preserved() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "memory.py").read_text(encoding="utf-8")
    service = (ROOT / "webapp_services" / "memory.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert "build_memory_page as build_memory_page_html" not in legacy
    assert "build_memory_page as build_memory_page_html" in route
    assert 'level: str = Query(default="medium")' in route
    assert "banner_url=CARDS_TOP_BANNER_URL" in entrypoint

    assert 'MEMORY_LEVELS = frozenset({"easy", "medium", "hard", "extreme"})' in service
    assert "MAX_MEMORY_TIME_MS = 7_200_000" in service
    assert "MAX_MEMORY_MOVES = 10_000" in service
    assert 'raise ValueError("Nivel invalido.")' in service
    assert 'raise ValueError("Tempo invalido.")' in service
    assert 'raise ValueError("Quantidade de jogadas invalida.")' in service

    assert '"new_record": bool(result.get("new_record"))' in service
    assert '"levels_completed"' in service
    assert '"avg_best_time_ms"' in service
    assert '"avg_best_moves"' in service
    assert '"completed_games"' in service
