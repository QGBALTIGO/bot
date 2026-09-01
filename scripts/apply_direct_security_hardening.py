from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prune_unreachable_function_tails(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    lines = text.splitlines(keepends=True)
    spans: list[tuple[int, int, str]] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        terminal_index = next(
            (
                index
                for index, statement in enumerate(node.body)
                if isinstance(statement, (ast.Return, ast.Raise))
            ),
            None,
        )
        if terminal_index is None or terminal_index >= len(node.body) - 1:
            continue

        first_dead_statement = node.body[terminal_index + 1]
        spans.append(
            (
                first_dead_statement.lineno - 1,
                int(node.end_lineno or first_dead_statement.end_lineno),
                node.name,
            )
        )

    if not spans:
        print(f"{path}: no unreachable function tails found")
        return 0, 0

    removed_lines = sum(end - start for start, end, _ in spans)
    if len(spans) != 17 or removed_lines < 5_000:
        details = ", ".join(name for _, _, name in spans)
        raise RuntimeError(
            f"Unexpected cleanup scope: functions={len(spans)} "
            f"lines={removed_lines} names={details}"
        )

    for start, end, _ in sorted(spans, reverse=True):
        del lines[start:end]

    path.write_text("".join(lines), encoding="utf-8")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return len(spans), removed_lines


def main() -> None:
    functions, lines = prune_unreachable_function_tails(ROOT / "webapp.py")
    print(f"unreachable_functions_cleaned={functions}")
    print(f"unreachable_lines_removed={lines}")


if __name__ == "__main__":
    main()
