from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def remove_shadowed_top_level_function(path: Path, function_name: str) -> int:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) <= 1:
        return 0

    lines = text.splitlines(keepends=True)
    removed = 0
    for node in reversed(matches[:-1]):
        start = max(0, node.lineno - 1)
        end = int(node.end_lineno or node.lineno)

        while start > 0 and not lines[start - 1].strip():
            start -= 1
        while end < len(lines) and not lines[end].strip():
            end += 1

        del lines[start:end]
        removed += 1

    path.write_text("".join(lines), encoding="utf-8")
    return removed


def main() -> None:
    target = ROOT / "premium_webapp_ui.py"
    removed = remove_shadowed_top_level_function(target, "build_dado_page")
    print(f"removed_shadowed_build_dado_page={removed}")
    if removed != 1:
        raise SystemExit(
            "Esperava remover exatamente uma definição antiga de build_dado_page; "
            f"resultado={removed}"
        )


if __name__ == "__main__":
    main()
