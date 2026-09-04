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
        calls_identity = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "_identity"
            for child in ast.walk(node)
        )
        assert calls_identity, f"{route} must call the signed identity resolver"

    assert found == PRIVATE_ROUTES


def test_v2_router_uses_shared_secure_resolver() -> None:
    text = Path("webapp_routes/source_v2_compat.py").read_text(encoding="utf-8")
    assert "from utils.webapp_identity import resolve_webapp_user" in text
    assert "ALLOW_INSECURE_WEBAPP_UID_FALLBACK" not in text
    assert "x_telegram_init_data" in text


def test_v2_frontend_sends_telegram_init_data_header() -> None:
    text = Path("frontend/src/api/client.ts").read_text(encoding="utf-8")
    assert "headers['X-Telegram-Init-Data'] = tg.initData" in text
    assert "headers['X-WebApp-Uid'] = String(telegramUserId)" in text
