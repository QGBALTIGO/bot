from __future__ import annotations

import ast
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-context-extraction.yml")
SELF = Path(__file__)


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(WEBAPP))

    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "api_webapp_context"
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one api_webapp_context function, found {len(matches)}")

    node = matches[0]
    decorator_lines = [decorator.lineno for decorator in node.decorator_list]
    start_line = min(decorator_lines or [node.lineno])
    end_line = int(node.end_lineno or node.lineno)

    lines = text.splitlines(keepends=True)
    start_index = start_line - 1
    end_index = end_line
    while end_index < len(lines) and not lines[end_index].strip():
        end_index += 1

    text = "".join(lines[:start_index] + lines[end_index:])

    if '@app.get("/api/webapp/context")' in text or "def api_webapp_context(" in text:
        raise SystemExit("legacy WebApp context route still present after extraction")

    WEBAPP.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
