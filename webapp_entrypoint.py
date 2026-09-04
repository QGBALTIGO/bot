from __future__ import annotations

from webapp import app
from utils.health_routes import router as health_router


def _install_runtime_routes() -> None:
    registered_paths = {getattr(route, "path", "") for route in app.routes}
    if "/health" not in registered_paths or "/api/health" not in registered_paths:
        app.include_router(health_router)


_install_runtime_routes()
