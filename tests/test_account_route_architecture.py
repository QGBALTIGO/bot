from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_delete_account_route_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "account.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.post("/api/menu/delete-account")' not in legacy
    assert '@router.post("/api/menu/delete-account")' in route
    assert "from webapp_routes.account import router as account_router" in entrypoint
    assert "app.include_router(account_router)" in entrypoint


def test_delete_account_route_keeps_signed_identity_contract() -> None:
    route = (ROOT / "webapp_routes" / "account.py").read_text(encoding="utf-8")

    assert "resolve_webapp_user as _resolve_webapp_user" in route
    assert "x_telegram_init_data=x_telegram_init_data" in route
    assert "x_webapp_uid=x_webapp_uid" in route
    assert 'body_uid=payload.get("uid")' in route
    assert 'delete_user_account(int(ctx["user_id"]))' in route
    assert 'return {"ok": True}' in route


def test_account_transaction_remains_in_database_for_separate_refactor() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    database = (ROOT / "database.py").read_text(encoding="utf-8")
    route = (ROOT / "webapp_routes" / "account.py").read_text(encoding="utf-8")

    assert "delete_user_account," not in legacy
    assert "def delete_user_account(" in database
    assert "from database import delete_user_account" in route
    assert "with pool.connection() as conn:" in database
