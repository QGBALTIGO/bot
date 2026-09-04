from __future__ import annotations

from webapp import app
from utils.health_routes import router as health_router
from utils.request_observability import RequestObservabilityMiddleware
from webapp_routes.image_proxy import router as image_proxy_router


def _install_runtime_routes() -> None:
    registered_paths = {getattr(route, "path", "") for route in app.routes}

    if "/health" not in registered_paths or "/api/health" not in registered_paths:
        app.include_router(health_router)
        registered_paths.update({"/health", "/api/health"})

    if "/api/image-proxy" not in registered_paths:
        app.include_router(image_proxy_router)


def _install_runtime_middleware() -> None:
    if any(
        middleware.cls is RequestObservabilityMiddleware
        for middleware in app.user_middleware
    ):
        return
    app.add_middleware(RequestObservabilityMiddleware)


_install_runtime_routes()
_install_runtime_middleware()
