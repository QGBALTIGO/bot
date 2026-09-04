from __future__ import annotations

import ast
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-profile-settings-extraction.yml")
SELF = Path(__file__)

TARGETS = {
    "api_menu_language",
    "api_menu_privacy",
    "api_menu_notifications",
}

ROUTE_MARKERS = {
    '@app.post("/api/menu/language")',
    '@app.post("/api/menu/privacy")',
    '@app.post("/api/menu/notifications")',
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
        raise SystemExit(f"profile setting routes not found: {missing}")

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

    for marker in ROUTE_MARKERS:
        if marker in text:
            raise SystemExit(f"legacy profile route still present: {marker}")
    for name in TARGETS:
        if f"def {name}(" in text:
            raise SystemExit(f"legacy profile handler still present: {name}")

    # Rotas acopladas a coleção/exclusão permanecem para etapas posteriores.
    for marker in (
        '@app.get("/api/menu/profile")',
        '@app.get("/api/menu/collection-characters")',
        '@app.post("/api/menu/nickname")',
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
