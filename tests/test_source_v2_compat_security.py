from __future__ import annotations

import ast
from pathlib import Path


PRIVATE_ROUTES = {
    "/me",
    "/harem",
    "/gallery",
    "/social/marriage",
    "/battle/stats",
    "/achievements/list",
    "/quests",
    "/quests/claim/{quest_id}",
}


def _route_path(node: ast.FunctionDef) -> str | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not isinstance(func, ast.Attribute) or func.attr not in {"get", "post", "put", "delete"}:
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            value = decorator.args[0].value
            if isinstance(value, str):
                return value
    return None


def test_private_v2_routes_resolve_signed_identity() -> None:
    path = Path("webapp_routes/source_v2_compat.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    found = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route = _route_path(node)
        if route not in PRIVATE_ROUTES:
            continue
        found.add(route)
        identity_calls = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        assert "_private_identity" in identity_calls or "_identity" in identity_calls, (
            f"{route} must call the signed/session identity resolver"
        )

    assert found == PRIVATE_ROUTES


def test_v2_router_uses_shared_secure_resolver() -> None:
    path = Path("webapp_routes/source_v2_compat.py")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    imports_from_identity = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "utils.webapp_identity":
            imports_from_identity.update(alias.name for alias in node.names)

    assert "resolve_webapp_user" in imports_from_identity
    assert "build_fallback_webapp_user" in imports_from_identity
    assert "get_tg_user" in imports_from_identity
    assert "ALLOW_INSECURE_WEBAPP_UID_FALLBACK" not in text
    assert "x_telegram_init_data" in text
    assert "validate_session_token" in text


def test_exact_seal_frontend_uses_secure_init_and_bearer_session() -> None:
    text = Path("frontend/src/api/client.ts").read_text(encoding="utf-8")
    assert "const initData = tg?.initData;" in text
    assert "body: JSON.stringify(payload)" in text
    assert "`${API_BASE}/secure_init`" in text
    assert "headers.Authorization = `Bearer ${sessionToken}`" in text
