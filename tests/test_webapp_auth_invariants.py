from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP_PATH = ROOT / "webapp.py"
PREMIUM_UI_PATH = ROOT / "premium_webapp_ui.py"


def _route_functions() -> dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(WEBAPP_PATH.read_text(encoding="utf-8"), filename=str(WEBAPP_PATH))
    routes: dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            path = decorator.args[0].value
            if isinstance(path, str):
                routes[(method, path)] = node
    return routes


def _calls(function: ast.FunctionDef | ast.AsyncFunctionDef, target: str) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == target:
                return True
    return False


def test_sensitive_dado_and_profile_routes_require_signed_webapp_identity() -> None:
    routes = _route_functions()
    protected = {
        ("GET", "/api/dado/state"),
        ("POST", "/api/dado/roll"),
        ("POST", "/api/dado/pick"),
        ("GET", "/api/menu/profile"),
        ("GET", "/api/menu/collection-characters"),
        ("POST", "/api/menu/nickname"),
        ("POST", "/api/menu/favorite"),
        ("POST", "/api/menu/country"),
        ("POST", "/api/menu/language"),
        ("POST", "/api/menu/privacy"),
        ("POST", "/api/menu/notifications"),
        ("POST", "/api/menu/delete-account"),
        ("GET", "/api/webapp/context"),
    }

    missing = sorted(route for route in protected if route not in routes)
    assert not missing, f"Rotas privadas desapareceram ou mudaram sem atualizar os testes: {missing}"

    unprotected = sorted(
        route
        for route in protected
        if not _calls(routes[route], "_resolve_webapp_user")
    )
    assert not unprotected, (
        "Rotas privadas sem _resolve_webapp_user permitem regressão de identidade: "
        f"{unprotected}"
    )


def test_shared_miniapp_client_sends_telegram_init_data() -> None:
    text = PREMIUM_UI_PATH.read_text(encoding="utf-8")
    assert 'headers["x-telegram-init-data"] = initData;' in text
    assert "Telegram.WebApp" in text


def test_insecure_uid_fallback_is_opt_in_only() -> None:
    text = WEBAPP_PATH.read_text(encoding="utf-8")
    assert '"ALLOW_INSECURE_WEBAPP_UID_FALLBACK"' in text
    assert 'raise HTTPException(status_code=401, detail="telegram_init_data_required")' in text


def test_dado_reward_failures_keep_refund_paths() -> None:
    routes = _route_functions()
    pick = routes[("POST", "/api/dado/pick")]
    source = ast.get_source_segment(
        WEBAPP_PATH.read_text(encoding="utf-8"),
        pick,
    ) or ""
    assert "cancel_dice_roll" in source
    assert '"refunded": True' in source
