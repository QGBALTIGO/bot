from __future__ import annotations

import ast
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-auth-core-extraction.yml")
SELF = Path(__file__)

OLD_IMPORT = (
    "from utils.telegram_webapp_auth import TelegramWebAppAuthError, validate_telegram_init_data\n"
)
NEW_IMPORT = """from utils.webapp_identity import (
    build_fallback_webapp_user as _build_fallback_webapp_user,
    coerce_positive_uid as _coerce_positive_uid,
    get_tg_user as _get_tg_user,
    resolve_webapp_user as _resolve_webapp_user,
    verify_telegram_init_data,
)
"""

AUTH_FUNCTIONS = {
    "verify_telegram_init_data",
    "_get_tg_user",
    "_coerce_positive_uid",
    "_build_fallback_webapp_user",
    "_resolve_webapp_user",
}


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")

    import_count = text.count(OLD_IMPORT)
    if import_count != 1:
        raise SystemExit(f"expected exactly one legacy Telegram auth import, found {import_count}")
    text = text.replace(OLD_IMPORT, NEW_IMPORT, 1)

    tree = ast.parse(text, filename=str(WEBAPP))
    nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in AUTH_FUNCTIONS
    }
    missing = sorted(AUTH_FUNCTIONS - set(nodes))
    if missing:
        raise SystemExit(f"auth functions not found: {missing}")

    lines = text.splitlines(keepends=True)
    header_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "# TELEGRAM WEBAPP AUTH"),
        None,
    )
    if header_index is None:
        raise SystemExit("Telegram WebApp auth header not found")

    start_index = header_index
    if start_index > 0 and lines[start_index - 1].strip().startswith("# ==="):
        start_index -= 1

    resolver = nodes["_resolve_webapp_user"]
    end_index = int(resolver.end_lineno or resolver.lineno)
    while end_index < len(lines) and not lines[end_index].strip():
        end_index += 1

    text = "".join(lines[:start_index] + lines[end_index:])

    forbidden = tuple(f"def {name}(" for name in AUTH_FUNCTIONS)
    for marker in forbidden:
        if marker in text:
            raise SystemExit(f"legacy auth implementation still present: {marker}")

    if "resolve_webapp_user as _resolve_webapp_user" not in text:
        raise SystemExit("shared identity resolver import was not installed")

    WEBAPP.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
