from __future__ import annotations

from webapp import (
    REQUIRED_CHANNEL,
    _collection_cards_from_snapshot,
    _collection_snapshot,
    _require_internal_api_secret,
    app,
)
from utils.health_routes import router as health_router
from utils.request_observability import RequestObservabilityMiddleware
from utils.webapp_identity import resolve_webapp_user
from webapp_routes.channel import build_channel_router
from webapp_routes.context import build_context_router
from webapp_routes.image_proxy import router as image_proxy_router

channel_router = build_channel_router(
    resolve_webapp_user=resolve_webapp_user,
    require_internal_api_secret=_require_internal_api_secret,
    required_channel=REQUIRED_CHANNEL,
)
context_router = build_context_router(
    collection_snapshot=_collection_snapshot,
    collection_cards_from_snapshot=_collection_cards_from_snapshot,
)


def _install_runtime_routes() -> None:
    registered_paths = {getattr(route, "path", "") for route in app.routes}

    if "/health" not in registered_paths or "/api/health" not in registered_paths:
        app.include_router(health_router)
        registered_paths.update({"/health", "/api/health"})

    if "/api/image-proxy" not in registered_paths:
        app.include_router(image_proxy_router)
        registered_paths.add("/api/image-proxy")

    if "/api/channel/selftest" not in registered_paths or "/api/channel/check" not in registered_paths:
        app.include_router(channel_router)
        registered_paths.update({"/api/channel/selftest", "/api/channel/check"})

    if "/api/webapp/context" not in registered_paths:
        app.include_router(context_router)


def _install_runtime_middleware() -> None:
    if any(
        middleware.cls is RequestObservabilityMiddleware
        for middleware in app.user_middleware
    ):
        return
    app.add_middleware(RequestObservabilityMiddleware)


_install_runtime_routes()
_install_runtime_middleware()
