from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DuplicateRoute:
    path: str
    methods: tuple[str, ...]
    removed_name: str
    kept_name: str


def _route_key(route: Any):
    path = str(getattr(route, "path", "") or "")
    methods = getattr(route, "methods", None)
    endpoint = getattr(route, "endpoint", None)

    # Only deduplicate normal HTTP routes. Mounts, websocket routes and other
    # Starlette internals are left untouched.
    if not path or not methods or endpoint is None:
        return None

    normalized_methods = tuple(sorted(str(method).upper() for method in methods))
    if not normalized_methods:
        return None

    return path, normalized_methods


def dedupe_http_routes_keep_last(app: Any) -> list[DuplicateRoute]:
    """Remove duplicate HTTP path+method registrations, keeping the newest one.

    FastAPI/Starlette resolves routes in registration order. In the legacy
    WebApp, old route implementations were left above newer replacements, so
    the old function won forever and the newer code became unreachable.

    During the V2 migration we intentionally keep the LAST registration. This
    makes the intended newer implementation active while the monolithic file is
    being split into routers. Every removal is returned/logged for auditability.
    """

    router = getattr(app, "router", None)
    routes = list(getattr(router, "routes", []) or [])
    if not router or not routes:
        return []

    seen: dict[tuple[str, tuple[str, ...]], Any] = {}
    kept_reversed: list[Any] = []
    removed: list[DuplicateRoute] = []

    for route in reversed(routes):
        key = _route_key(route)
        if key is None:
            kept_reversed.append(route)
            continue

        if key not in seen:
            seen[key] = route
            kept_reversed.append(route)
            continue

        newer = seen[key]
        removed.append(
            DuplicateRoute(
                path=key[0],
                methods=key[1],
                removed_name=str(getattr(route, "name", "") or getattr(getattr(route, "endpoint", None), "__name__", "")),
                kept_name=str(getattr(newer, "name", "") or getattr(getattr(newer, "endpoint", None), "__name__", "")),
            )
        )

    router.routes[:] = list(reversed(kept_reversed))

    for item in reversed(removed):
        logger.warning(
            "Rota HTTP duplicada removida: methods=%s path=%s old=%s kept=%s",
            ",".join(item.methods),
            item.path,
            item.removed_name,
            item.kept_name,
        )

    if removed:
        logger.warning("Total de rotas HTTP duplicadas removidas no bootstrap: %s", len(removed))

    return list(reversed(removed))
