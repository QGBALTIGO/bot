from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "commands" / "cards_admin.py"
GENERIC_MESSAGE = "❌ Não foi possível concluir a operação administrativa. O erro foi registrado."


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "unknown"


def _contains_exception_leak(source: str, variable: str) -> bool:
    if not variable:
        return False
    if not any(marker in source for marker in ("_reply(", "reply_text(", "reply_html(")):
        return False
    escaped = re.escape(variable)
    return bool(
        re.search(rf"\{{\s*{escaped}(?:\s*[!:][^}}]*)?\s*\}}", source)
        or re.search(rf"\bstr\s*\(\s*{escaped}\s*\)", source)
    )


def _ensure_logging(text: str) -> str:
    if "import logging\n" not in text:
        import_anchor = "import os\n"
        if import_anchor not in text:
            raise RuntimeError("Não encontrei o bloco de imports de cards_admin.py")
        text = text.replace(import_anchor, "import logging\n" + import_anchor, 1)

    if "logger = logging.getLogger(__name__)" not in text:
        config_anchor = "CARD_ADMIN_IDS = {"
        if config_anchor not in text:
            raise RuntimeError("Não encontrei CARD_ADMIN_IDS em cards_admin.py")
        text = text.replace(
            config_anchor,
            "logger = logging.getLogger(__name__)\n\n" + config_anchor,
            1,
        )
    return text


def harden() -> int:
    original = TARGET.read_text(encoding="utf-8")
    text = _ensure_logging(original)
    tree = ast.parse(text, filename=str(TARGET))

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    lines = text.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not node.body or not node.name:
            continue

        first = node.body[0]
        last = node.body[-1]
        start = first.lineno - 1
        end = int(last.end_lineno or last.lineno)
        body_source = "".join(lines[start:end])
        if not _contains_exception_leak(body_source, node.name):
            continue

        function_name = _enclosing_function(node, parents)
        indent = " " * int(first.col_offset)
        replacement = (
            f'{indent}logger.exception("Falha no comando administrativo {function_name}")\n'
            f'{indent}await _reply(update, "{GENERIC_MESSAGE}")\n'
        )
        replacements.append((start, end, replacement))

    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]

    updated = "".join(lines)
    ast.parse(updated, filename=str(TARGET))

    leak_pattern = re.compile(
        r"(?:_reply|reply_text|reply_html)\s*\([^\n]*\{\s*(?:e|exc|error)\s*(?:[!:][^}]*)?\}",
        re.IGNORECASE,
    )
    if leak_pattern.search(updated):
        raise RuntimeError("Ainda existe uma exceção interpolada em resposta administrativa")

    TARGET.write_text(updated, encoding="utf-8")
    print(f"admin_exception_handlers_hardened={len(replacements)}")
    return len(replacements)


def main() -> None:
    changed = harden()
    if changed <= 0:
        raise SystemExit("Nenhum handler vulnerável foi encontrado; transformação não aplicada")


if __name__ == "__main__":
    main()
