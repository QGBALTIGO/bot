from __future__ import annotations

import ast
from pathlib import Path

WEBAPP = Path("webapp.py")
WORKFLOW = Path(".github/workflows/apply-webapp-profile-country-extraction.yml")
SELF = Path(__file__)

IMPORT_ANCHOR = "from utils.webapp_identity import (\n"
OPTIONS_IMPORT = "from utils.profile_options import COUNTRY_OPTIONS, LANGUAGE_OPTIONS\n"


def _assignment(tree: ast.Module, name: str) -> ast.Assign:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one assignment for {name}, found {len(matches)}")
    return matches[0]


def main() -> None:
    text = WEBAPP.read_text(encoding="utf-8")
    if OPTIONS_IMPORT not in text:
        if IMPORT_ANCHOR not in text:
            raise SystemExit("webapp identity import anchor not found")
        text = text.replace(IMPORT_ANCHOR, OPTIONS_IMPORT + IMPORT_ANCHOR, 1)

    tree = ast.parse(text, filename=str(WEBAPP))
    targets = {
        "COUNTRY_OPTIONS": _assignment(tree, "COUNTRY_OPTIONS"),
        "LANGUAGE_OPTIONS": _assignment(tree, "LANGUAGE_OPTIONS"),
    }
    country_handlers = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "api_menu_country"
    ]
    if len(country_handlers) != 1:
        raise SystemExit(f"expected one api_menu_country function, found {len(country_handlers)}")

    lines = text.splitlines(keepends=True)
    ranges: list[tuple[int, int, str]] = []
    for name, node in targets.items():
        ranges.append((node.lineno - 1, int(node.end_lineno or node.lineno), name))

    route = country_handlers[0]
    start_line = min([d.lineno for d in route.decorator_list] + [route.lineno])
    ranges.append((start_line - 1, int(route.end_lineno or route.lineno), "api_menu_country"))

    for start, end, _name in sorted(ranges, reverse=True):
        while end < len(lines) and not lines[end].strip():
            end += 1
        del lines[start:end]

    text = "".join(lines)
    if '@app.post("/api/menu/country")' in text:
        raise SystemExit("legacy country route still present")
    if "COUNTRY_OPTIONS = [" in text or "LANGUAGE_OPTIONS = [" in text:
        raise SystemExit("legacy profile option constants still present")
    if OPTIONS_IMPORT.strip() not in text:
        raise SystemExit("shared profile options import missing")

    for marker in (
        '@app.get("/api/menu/profile")',
        '@app.get("/api/menu/collection-characters")',
        '@app.post("/api/menu/favorite")',
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
