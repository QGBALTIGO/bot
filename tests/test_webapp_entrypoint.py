from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "webapp_entrypoint.py"


def test_production_entrypoint_installs_health_router() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(ENTRYPOINT))

    imported_webapp = False
    imported_health_router = False
    include_router = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "webapp":
            imported_webapp = any(alias.name == "app" for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module == "utils.health_routes":
            imported_health_router = any(alias.name == "router" for alias in node.names)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
        ):
            include_router = True

    assert imported_webapp
    assert imported_health_router
    assert include_router


def test_readme_documents_web_only_entrypoint() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uvicorn webapp_entrypoint:app" in text
    assert "GET /health" in text
