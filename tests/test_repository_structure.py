from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _python_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not any(part in EXCLUDED_PARTS for part in path.parts)
    )


def test_python_sources_parse() -> None:
    errors: list[str] = []
    for path in _python_files():
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    assert not errors, "Arquivos Python inválidos:\n" + "\n".join(errors)


def test_no_shadowed_top_level_definitions() -> None:
    duplicates: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        definitions: dict[str, list[int]] = defaultdict(list)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions[node.name].append(node.lineno)

        for name, lines in definitions.items():
            if len(lines) > 1:
                duplicates.append(
                    f"{path.relative_to(ROOT)}: {name} definido nas linhas {lines}"
                )

    assert not duplicates, (
        "Definições de topo duplicadas sobrescrevem código silenciosamente:\n"
        + "\n".join(duplicates)
    )
