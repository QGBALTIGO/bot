from __future__ import annotations

import ast
from pathlib import Path


def main() -> None:
    path = Path("webapp.py")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    assignment_names = {
        "CATALOG_PATH",
        "CATALOG_BANNER_URL",
        "BACKGROUND_PATTERN_URL",
        "CATALOG_TITLE",
        "CATALOG_SUBTITLE",
        "_CATALOG",
        "_LETTER_COUNTS",
        "_TOTAL",
        "MANGA_CATALOG_PATH",
        "MANGA_CATALOG_BANNER_URL",
        "MANGA_BACKGROUND_PATTERN_URL",
        "MANGA_CATALOG_TITLE",
        "MANGA_CATALOG_SUBTITLE",
        "_MANGA_CATALOG",
        "_MANGA_LETTER_COUNTS",
        "_MANGA_TOTAL",
    }
    helper_names = {
        "_normalize_title",
        "_first_letter",
        "_safe_int",
        "_unwrap_records",
        "_coerce_item",
        "_load_catalog",
        "_filter_catalog",
        "_detect_manga_badge",
        "_coerce_manga_item",
        "_load_manga_catalog",
        "_filter_manga_catalog",
    }
    route_names = {
        "api_letters",
        "api_catalogo",
        "catalogo_page",
        "api_mangas_letters",
        "api_mangas_catalogo",
        "mangas_page",
    }
    removable_functions = helper_names | route_names

    assignments: dict[str, ast.AST] = {}
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    startup_tries: list[ast.Try] = []

    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in assignment_names:
                    assignments[target.id] = node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in removable_functions:
                functions[node.name] = node
        elif isinstance(node, ast.Try):
            called = {
                child.func.id
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            if "_load_catalog" in called or "_load_manga_catalog" in called:
                startup_tries.append(node)

    missing_assignments = assignment_names - assignments.keys()
    missing_functions = removable_functions - functions.keys()
    if missing_assignments or missing_functions or len(startup_tries) != 2:
        raise SystemExit(
            "Abortando: domínio de catálogo mudou inesperadamente: "
            f"assignments={sorted(missing_assignments)}, "
            f"functions={sorted(missing_functions)}, startup_tries={len(startup_tries)}"
        )

    owners = [
        (node.lineno, node.end_lineno or node.lineno, node.name)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def owner_for(lineno: int) -> str:
        for start, end, name in owners:
            if start <= lineno <= end:
                return name
        return "<module>"

    def loads_of(symbol: str) -> list[tuple[int, str]]:
        return [
            (node.lineno, owner_for(node.lineno))
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id == symbol
            and isinstance(node.ctx, ast.Load)
        ]

    unwrap_outside = [
        item
        for item in loads_of("_unwrap_records")
        if item[1] not in {"_load_catalog", "_load_manga_catalog"}
    ]
    if not unwrap_outside or any(owner != "_pedido_reload_indexes" for _, owner in unwrap_outside):
        raise SystemExit(
            "Abortando: consumidores externos de _unwrap_records mudaram: "
            f"{unwrap_outside}"
        )

    for symbol in helper_names - {"_unwrap_records", "_load_catalog", "_load_manga_catalog"}:
        outside = [
            item for item in loads_of(symbol)
            if item[1] not in removable_functions
        ]
        if outside:
            raise SystemExit(f"Abortando: {symbol} possui consumidores externos: {outside}")

    for symbol in {"_load_catalog", "_load_manga_catalog"}:
        outside = [
            item for item in loads_of(symbol)
            if item[1] not in removable_functions and item[1] != "<module>"
        ]
        if outside:
            raise SystemExit(f"Abortando: {symbol} possui consumidores externos: {outside}")

    builder_outside = [
        item for item in loads_of("build_media_catalog_page_html")
        if item[1] not in {"catalogo_page", "mangas_page"}
    ]
    if builder_outside:
        raise SystemExit(
            "Abortando: builder compartilhado do catálogo possui consumidores externos: "
            f"{builder_outside}"
        )

    allowed_config_owners = {
        "CATALOG_PATH": {"_load_catalog"},
        "CATALOG_BANNER_URL": {"catalogo_page", "home"},
        "BACKGROUND_PATTERN_URL": set(),
        "CATALOG_TITLE": {"catalogo_page"},
        "CATALOG_SUBTITLE": set(),
        "_CATALOG": {"_load_catalog", "_filter_catalog"},
        "_LETTER_COUNTS": {"_load_catalog", "api_letters"},
        "_TOTAL": {"_load_catalog", "api_letters"},
        "MANGA_CATALOG_PATH": {"_load_manga_catalog"},
        "MANGA_CATALOG_BANNER_URL": {"mangas_page", "home"},
        "MANGA_BACKGROUND_PATTERN_URL": set(),
        "MANGA_CATALOG_TITLE": {"mangas_page"},
        "MANGA_CATALOG_SUBTITLE": set(),
        "_MANGA_CATALOG": {"_load_manga_catalog", "_filter_manga_catalog"},
        "_MANGA_LETTER_COUNTS": {"_load_manga_catalog", "api_mangas_letters"},
        "_MANGA_TOTAL": {"_load_manga_catalog", "api_mangas_letters"},
    }
    for symbol, allowed in allowed_config_owners.items():
        outside = [item for item in loads_of(symbol) if item[1] not in allowed]
        if outside:
            raise SystemExit(f"Abortando: config {symbol} possui usos inesperados: {outside}")

    unwrap_source = ast.get_source_segment(text, functions["_unwrap_records"]) or ""
    if not unwrap_source.startswith("def _unwrap_records("):
        raise SystemExit("Abortando: não foi possível extrair _unwrap_records literalmente")
    utility_text = (
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict, List\n\n\n"
        + unwrap_source.replace("def _unwrap_records(", "def unwrap_records(", 1)
        + "\n"
    )
    utility_path = Path("utils/catalog_records.py")
    if utility_path.exists():
        raise SystemExit("Abortando: utils/catalog_records.py já existe inesperadamente")
    utility_path.write_text(utility_text, encoding="utf-8")
    ast.parse(utility_text, filename=str(utility_path))

    service_assignment_order = sorted(
        (node.lineno, name, node) for name, node in assignments.items()
    )
    service_function_names = helper_names - {"_unwrap_records"}
    service_function_order = sorted(
        (functions[name].lineno, name, functions[name]) for name in service_function_names
    )
    service_try_order = sorted(startup_tries, key=lambda node: node.lineno)

    original_parts: list[str] = []
    for _, _, node in service_assignment_order:
        original_parts.append(ast.get_source_segment(text, node) or "")
    for _, _, node in service_function_order:
        original_parts.append(ast.get_source_segment(text, node) or "")
    for node in service_try_order:
        original_parts.append(ast.get_source_segment(text, node) or "")
    if any(not part.strip() for part in original_parts):
        raise SystemExit("Abortando: falha ao extrair algum trecho original do catálogo")

    wrappers = '''


def catalog_letters_payload() -> Dict[str, Any]:
    letters = ["ALL", "#"] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    return {
        "total": _TOTAL,
        "counts": {k: _LETTER_COUNTS.get(k, 0) for k in letters if k not in ("ALL")},
        "all_count": _TOTAL,
    }


def manga_letters_payload() -> Dict[str, Any]:
    letters = ["ALL", "#"] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    return {
        "total": _MANGA_TOTAL,
        "counts": {k: _MANGA_LETTER_COUNTS.get(k, 0) for k in letters if k not in ("ALL")},
        "all_count": _MANGA_TOTAL,
    }


def filter_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    return _filter_catalog(q=q, letter=letter, limit=limit, offset=offset)


def filter_manga_catalog(q: str, letter: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    return _filter_manga_catalog(q=q, letter=letter, limit=limit, offset=offset)
'''

    service_text = (
        "from __future__ import annotations\n\n"
        "import json\n"
        "import os\n"
        "import re\n"
        "import traceback\n"
        "from typing import Any, Dict, List, Optional, Tuple\n\n"
        "from utils.catalog_records import unwrap_records as _unwrap_records\n\n\n"
        + "\n\n\n".join(original_parts)
        + wrappers
    )
    service_path = Path("webapp_services/catalog.py")
    if service_path.exists():
        raise SystemExit("Abortando: webapp_services/catalog.py já existe inesperadamente")
    service_path.write_text(service_text, encoding="utf-8")
    ast.parse(service_text, filename=str(service_path))

    ranges: list[tuple[int, int, str]] = []
    for name, node in assignments.items():
        ranges.append((node.lineno, node.end_lineno or node.lineno, name))
    for name, node in functions.items():
        start = min([d.lineno for d in node.decorator_list] + [node.lineno])
        ranges.append((start, node.end_lineno or node.lineno, name))
    for index, node in enumerate(startup_tries, 1):
        ranges.append((node.lineno, node.end_lineno or node.lineno, f"startup_try_{index}"))

    lines = text.splitlines(keepends=True)
    for start, end, _ in sorted(ranges, reverse=True):
        del lines[start - 1:end]
    new_text = "".join(lines)

    builder_import = "    build_media_catalog_page as build_media_catalog_page_html,\n"
    if new_text.count(builder_import) != 1:
        raise SystemExit(
            "Abortando: import do builder de catálogo não é único: "
            f"{new_text.count(builder_import)}"
        )
    new_text = new_text.replace(builder_import, "", 1)

    marker = "from webapp_services.terms import TERMS_VERSION\n"
    if marker not in new_text:
        raise SystemExit("Abortando: ponto de inserção dos imports de catálogo não encontrado")
    compatibility_imports = (
        "from utils.catalog_records import unwrap_records as _unwrap_records\n"
        "from webapp_services.catalog import CATALOG_BANNER_URL, MANGA_CATALOG_BANNER_URL\n"
    )
    new_text = new_text.replace(marker, marker + compatibility_imports, 1)

    parsed = ast.parse(new_text, filename=str(path))
    remaining_defs = {
        node.name
        for node in parsed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    leaked = removable_functions & remaining_defs
    if leaked:
        raise SystemExit(f"Abortando: funções legadas permaneceram: {sorted(leaked)}")

    for symbol in assignment_names:
        stores = [
            node.lineno
            for node in ast.walk(parsed)
            if isinstance(node, ast.Name)
            and node.id == symbol
            and isinstance(node.ctx, ast.Store)
        ]
        if stores:
            raise SystemExit(f"Abortando: assignment legado permaneceu para {symbol}: {stores}")

    unwrap_loads_after = [
        node.lineno
        for node in ast.walk(parsed)
        if isinstance(node, ast.Name)
        and node.id == "_unwrap_records"
        and isinstance(node.ctx, ast.Load)
    ]
    if len(unwrap_loads_after) != len(unwrap_outside):
        raise SystemExit(
            "Abortando: usos de _unwrap_records em Pedido mudaram após extração: "
            f"before={unwrap_outside}, after={unwrap_loads_after}"
        )

    path.write_text(new_text, encoding="utf-8")


if __name__ == "__main__":
    main()
