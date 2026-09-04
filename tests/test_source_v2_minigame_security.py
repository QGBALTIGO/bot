from __future__ import annotations

import ast
from pathlib import Path


PRIVATE_ROUTES = {
    "/minigames/state",
    "/minigames/start/{game_type}",
    "/minigames/submit",
}


def _route_path(node: ast.FunctionDef) -> str | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not isinstance(func, ast.Attribute) or func.attr not in {"get", "post"}:
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            value = decorator.args[0].value
            return value if isinstance(value, str) else None
    return None


def test_nexus_games_routes_use_shared_source_identity() -> None:
    path = Path("webapp_routes/source_v2_minigames.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route = _route_path(node)
        if route not in PRIVATE_ROUTES:
            continue
        found.add(route)
        calls = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        assert "_user_id" in calls, f"{route} must resolve authenticated user id"

    assert found == PRIVATE_ROUTES


def test_minigame_router_imports_central_auth_resolver() -> None:
    text = Path("webapp_routes/source_v2_minigames.py").read_text(encoding="utf-8")
    assert "from utils.source_v2_auth import resolve_source_v2_identity" in text
    assert "ALLOW_INSECURE_WEBAPP_UID_FALLBACK" not in text
