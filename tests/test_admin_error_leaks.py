from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "commands" / "avisar.py",
    ROOT / "commands" / "cards_admin.py",
    ROOT / "commands" / "dado_admin.py",
    ROOT / "commands" / "reset_users.py",
    ROOT / "commands" / "spawn_personagem.py",
)
USER_REPLY_METHODS = {
    "_reply",
    "reply_text",
    "reply_html",
    "reply_markdown",
    "edit_text",
    "edit_caption",
    "answer",
}


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _contains_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.Name) and child.id == name
        for child in ast.walk(node)
    )


def test_admin_handlers_do_not_expose_exception_objects() -> None:
    leaks: list[str] = []

    for path in TARGETS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for handler in (
            node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)
        ):
            exception_name = str(handler.name or "")
            if not exception_name:
                continue

            for node in handler.body:
                for call in (
                    child for child in ast.walk(node) if isinstance(child, ast.Call)
                ):
                    if _call_name(call) not in USER_REPLY_METHODS:
                        continue
                    values = [*call.args, *(kw.value for kw in call.keywords)]
                    if any(_contains_name(value, exception_name) for value in values):
                        leaks.append(
                            f"{path.relative_to(ROOT)}:{call.lineno} expõe "
                            f"a exceção '{exception_name}' ao usuário"
                        )

    assert not leaks, "\n".join(leaks)
