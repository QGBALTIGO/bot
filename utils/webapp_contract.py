from __future__ import annotations

from collections import Counter
from typing import Iterable


REQUIRED_WEBAPP_PAGES = {
    "/hub",
    "/game",
    "/collection",
    "/profile",
    "/ranking",
    "/shop-v2",
    "/xcards",
    "/memory",
    "/termo",
    "/messages",
    "/contrib",
    "/agenda",
    "/catalogo",
    "/mangas",
    "/cards",
    "/pedido",
    "/baltigoflix",
    "/terms",
    "/healthz",
}


def _route_keys(routes: Iterable[object]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for route in routes:
        path = str(getattr(route, "path", "") or "")
        methods = getattr(route, "methods", None) or set()
        if not path:
            continue
        for method in methods:
            method = str(method).upper()
            if method in {"HEAD", "OPTIONS"}:
                continue
            keys.append((method, path))
    return keys


def validate_webapp_routes(app, protected_paths: set[str]) -> dict[str, int]:
    """Fail startup when the final FastAPI surface is structurally inconsistent."""
    keys = _route_keys(getattr(app, "routes", []))
    counts = Counter(keys)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    if duplicates:
        joined = ", ".join(f"{method} {path}" for method, path in duplicates[:20])
        raise RuntimeError(f"Rotas WebApp duplicadas após bootstrap: {joined}")

    available_paths = {path for _, path in keys}
    missing_pages = sorted(REQUIRED_WEBAPP_PAGES - available_paths)
    if missing_pages:
        raise RuntimeError("Páginas WebApp ausentes: " + ", ".join(missing_pages))

    missing_protected = sorted(set(protected_paths) - available_paths)
    if missing_protected:
        raise RuntimeError("APIs protegidas sem rota registrada: " + ", ".join(missing_protected))

    return {
        "routes": len(keys),
        "pages": len(REQUIRED_WEBAPP_PAGES),
        "protected": len(protected_paths),
    }
