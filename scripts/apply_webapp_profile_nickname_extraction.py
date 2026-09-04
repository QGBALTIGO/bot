from __future__ import annotations

import ast
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-profile-nickname-extraction.yml")
SELF = Path(__file__)

TARGETS = {
    "_valid_menu_nickname",
    "api_menu_nickname",
}


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(WEBAPP))

    nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in TARGETS
    }
    missing = sorted(TARGETS - set(nodes))
    if missing:
        raise SystemExit(f"nickname targets not found: {missing}")

    lines = text.splitlines(keepends=True)
    ranges = []
    for name, node in nodes.items():
        start_line = min([d.lineno for d in node.decorator_list] + [node.lineno])
        end_line = int(node.end_lineno or node.lineno)
        ranges.append((start_line - 1, end_line, name))

    for start, end, _name in sorted(ranges, reverse=True):
        while end < len(lines) and not lines[end].strip():
            end += 1
        del lines[start:end]

    text = "".join(lines)

    if '@app.post("/api/menu/nickname")' in text:
        raise SystemExit("legacy nickname route still present")
    if "def _valid_menu_nickname(" in text:
        raise SystemExit("legacy nickname validator still present")

    for marker in (
        '@app.get("/api/menu/profile")',
        '@app.get("/api/menu/collection-characters")',
        '@app.post("/api/menu/favorite")',
        '@app.post("/api/menu/country")',
        '@app.post("/api/menu/delete-account")',
    ):
        if marker not in text:
            raise SystemExit(f"route removed unexpectedly: {marker}")

    WEBAPP.write_text(text, encoding="utf-8")

    for path in (WORKFLOW, SELF):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
