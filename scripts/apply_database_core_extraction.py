from __future__ import annotations

import ast
from pathlib import Path

DATABASE = Path("database.py")
WORKFLOW = Path(".github/workflows/apply-database-core-extraction.yml")
SELF = Path(__file__)

OLD_POOL_IMPORT = "from psycopg_pool import ConnectionPool\n"
NEW_CORE_IMPORT = "from database_core import DATABASE_URL, pool, run as _run\n"


def _top_level_assignment(tree: ast.Module, name: str) -> ast.Assign:
    matches: list[ast.Assign] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            matches.append(node)
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one top-level assignment for {name}, found {len(matches)}")
    return matches[0]


def main() -> None:
    text = DATABASE.read_text(encoding="utf-8")

    if text.count(OLD_POOL_IMPORT) != 1:
        raise SystemExit("legacy ConnectionPool import not found exactly once")
    text = text.replace(OLD_POOL_IMPORT, NEW_CORE_IMPORT, 1)

    tree = ast.parse(text, filename=str(DATABASE))
    database_url_node = _top_level_assignment(tree, "DATABASE_URL")
    pool_node = _top_level_assignment(tree, "pool")

    if database_url_node.lineno >= pool_node.lineno:
        raise SystemExit("unexpected database core ordering")

    lines = text.splitlines(keepends=True)
    setup_start = database_url_node.lineno - 1
    setup_end = int(pool_node.end_lineno or pool_node.lineno)
    while setup_end < len(lines) and not lines[setup_end].strip():
        setup_end += 1
    text = "".join(lines[:setup_start] + lines[setup_end:])

    tree = ast.parse(text, filename=str(DATABASE))
    run_nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_run"
    ]
    if len(run_nodes) != 1:
        raise SystemExit(f"expected exactly one _run definition, found {len(run_nodes)}")

    run_node = run_nodes[0]
    lines = text.splitlines(keepends=True)
    run_start = run_node.lineno - 1

    # Remove também o cabeçalho CORE SQL imediatamente associado, quando presente.
    cursor = run_start - 1
    while cursor >= 0 and not lines[cursor].strip():
        cursor -= 1
    if cursor >= 0 and lines[cursor].strip().startswith("# ==="):
        cursor -= 1
    if cursor >= 0 and lines[cursor].strip() == "# CORE SQL":
        cursor -= 1
        if cursor >= 0 and lines[cursor].strip().startswith("# ==="):
            run_start = cursor

    run_end = int(run_node.end_lineno or run_node.lineno)
    while run_end < len(lines) and not lines[run_end].strip():
        run_end += 1
    text = "".join(lines[:run_start] + lines[run_end:])

    if "ConnectionPool(" in text:
        raise SystemExit("ConnectionPool construction still present in database.py")
    if "def _run(" in text:
        raise SystemExit("legacy _run definition still present in database.py")
    if NEW_CORE_IMPORT.strip() not in text:
        raise SystemExit("database core import missing")

    DATABASE.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
