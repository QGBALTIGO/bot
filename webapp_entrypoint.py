from __future__ import annotations

from webapp import (
    CARDS_TOP_BANNER_URL,
    REQUIRED_CHANNEL,
    TOP_BANNER_URL,
    _require_internal_api_secret,
    app,
)
from utils.health_routes import router as health_router
from utils.request_observability import RequestObservabilityMiddleware
from utils.webapp_identity import resolve_webapp_user
from webapp_routes.account import router as account_router
from webapp_routes.channel import build_channel_router
from webapp_routes.collection import build_collection_router
from webapp_routes.context import build_context_router
from webapp_routes.image_proxy import router as image_proxy_router
from webapp_routes.profile_collection import router as profile_collection_router
from webapp_routes.profile_overview import build_profile_overview_router
from webapp_routes.profile_page import build_profile_page_router
from webapp_routes.profile_settings import router as profile_settings_router
from webapp_services.collection import (
    collection_cards_from_snapshot,
    collection_snapshot,
)

channel_router = build_channel_router(
    resolve_webapp_user=resolve_webapp_user,
    require_internal_api_secret=_require_internal_api_secret,
    required_channel=REQUIRED_CHANNEL,
)
context_router = build_context_router(
    collection_snapshot=collection_snapshot,
    collection_cards_from_snapshot=collection_cards_from_snapshot,
)
profile_overview_router = build_profile_overview_router(
    collection_snapshot=collection_snapshot,
    collection_cards_from_snapshot=collection_cards_from_snapshot,
)
profile_page_router = build_profile_page_router(
    default_banner_url=TOP_BANNER_URL,
)
collection_router = build_collection_router(
    banner_url=CARDS_TOP_BANNER_URL,
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
        registered_paths.add("/api/webapp/context")

    if "/menu" not in registered_paths:
        app.include_router(profile_page_router)
        registered_paths.add("/menu")

    if "/api/menu/profile" not in registered_paths:
        app.include_router(profile_overview_router)
        registered_paths.add("/api/menu/profile")

    profile_setting_paths = {
        "/api/menu/nickname",
        "/api/menu/country",
        "/api/menu/language",
        "/api/menu/privacy",
        "/api/menu/notifications",
    }
    if not profile_setting_paths.issubset(registered_paths):
        app.include_router(profile_settings_router)
        registered_paths.update(profile_setting_paths)

    profile_collection_paths = {
        "/api/menu/collection-characters",
        "/api/menu/favorite",
    }
    if not profile_collection_paths.issubset(registered_paths):
        app.include_router(profile_collection_router)
        registered_paths.update(profile_collection_paths)

    if "/api/menu/delete-account" not in registered_paths:
        app.include_router(account_router)
        registered_paths.add("/api/menu/delete-account")

    collection_paths = {
        "/cccolecao",
        "/api/collection/state",
        "/api/collection/cards",
        "/api/collection/animes",
        "/api/collection/anime",
    }
    if not collection_paths.issubset(registered_paths):
        app.include_router(collection_router)


def _install_runtime_middleware() -> None:
    if any(
        middleware.cls is RequestObservabilityMiddleware
        for middleware in app.user_middleware
    ):
        return
    app.add_middleware(RequestObservabilityMiddleware)


_install_runtime_routes()
_install_runtime_middleware()
