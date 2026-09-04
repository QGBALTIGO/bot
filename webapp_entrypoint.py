from __future__ import annotations

import os

from webapp import (
    BACKGROUND_URL,
    CARDS_TOP_BANNER_URL,
    EMPTY_BG_DATA_URI,
    REQUIRED_CHANNEL,
    REQUIRED_CHANNEL_URL,
    TOP_BANNER_URL,
    _require_internal_api_secret,
    app,
)
from utils.health_routes import router as health_router
from utils.request_observability import RequestObservabilityMiddleware
from utils.source_v2_frontend import install_source_v2_frontend
from utils.webapp_identity import resolve_webapp_user
from webapp_routes.account import router as account_router
from webapp_routes.channel import build_channel_router
from webapp_routes.collection import build_collection_router
from webapp_routes.context import build_context_router
from webapp_routes.image_proxy import router as image_proxy_router
from webapp_routes.memory import build_memory_router
from webapp_routes.profile_collection import router as profile_collection_router
from webapp_routes.profile_overview import build_profile_overview_router
from webapp_routes.profile_page import build_profile_page_router
from webapp_routes.profile_settings import router as profile_settings_router
from webapp_routes.source_v2_compat import router as source_v2_compat_router
from webapp_routes.terms import build_terms_router
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
memory_router = build_memory_router(
    banner_url=CARDS_TOP_BANNER_URL,
)
terms_router = build_terms_router(
    required_channel_url=REQUIRED_CHANNEL_URL,
    top_banner_url=TOP_BANNER_URL,
    background_url=BACKGROUND_URL,
    empty_bg_data_uri=EMPTY_BG_DATA_URI,
)


def _maybe_apply_v2_migrations() -> None:
    enabled = str(os.getenv("SOURCE_V2_AUTO_MIGRATE", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return

    from database_migrations import apply_migrations

    applied = apply_migrations()
    print(f"[source-v2] migrations ready; applied={applied}", flush=True)


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

    v2_compat_paths = {
        "/api/v1_7b82/secure_init",
        "/api/v1_7b82/bot/info",
        "/api/v1_7b82/me",
        "/api/v1_7b82/harem",
        "/api/v1_7b82/gallery",
        "/api/v1_7b82/rarities",
        "/api/v1_7b82/social/marriage",
        "/api/v1_7b82/battle/stats",
        "/api/v1_7b82/achievements/list",
        "/api/v1_7b82/compat/status",
    }
    if not v2_compat_paths.issubset(registered_paths):
        app.include_router(source_v2_compat_router)
        registered_paths.update(v2_compat_paths)

    terms_paths = {
        "/terms",
        "/api/terms/accept",
        "/api/terms/decline",
    }
    if not terms_paths.issubset(registered_paths):
        app.include_router(terms_router)
        registered_paths.update(terms_paths)

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
        registered_paths.update(collection_paths)

    memory_paths = {
        "/memoria",
        "/memory",
        "/api/memory/best",
        "/api/memory/finish",
    }
    if not memory_paths.issubset(registered_paths):
        app.include_router(memory_router)


def _install_runtime_middleware() -> None:
    if any(
        middleware.cls is RequestObservabilityMiddleware
        for middleware in app.user_middleware
    ):
        return
    app.add_middleware(RequestObservabilityMiddleware)


_maybe_apply_v2_migrations()
_install_runtime_routes()
_install_runtime_middleware()
install_source_v2_frontend(app)
