from __future__ import annotations

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
from utils.webapp_identity import resolve_webapp_user
from webapp_routes.account import router as account_router
from webapp_routes.aninexus_dado import build_aninexus_dado_router
from webapp_routes.aninexus_games import build_aninexus_games_router
from webapp_routes.aninexus_me import build_aninexus_me_router
from webapp_routes.aninexus_pets import build_aninexus_pets_router
from webapp_routes.aninexus_ranking import build_aninexus_ranking_router
from webapp_routes.aninexus_shop import build_aninexus_shop_router
from webapp_routes.aninexus_social import build_aninexus_social_router
from webapp_routes.channel import build_channel_router
from webapp_routes.collection import build_collection_router
from webapp_routes.context import build_context_router
from webapp_routes.image_proxy import router as image_proxy_router
from webapp_routes.memory import build_memory_router
from webapp_routes.profile_collection import router as profile_collection_router
from webapp_routes.profile_overview import build_profile_overview_router
from webapp_routes.profile_page import build_profile_page_router
from webapp_routes.profile_settings import router as profile_settings_router
from webapp_routes.aninexus_compat import build_aninexus_compat_router
from webapp_routes.aninexus_progression import build_aninexus_progression_router
from webapp_routes.aninexus_runtime import install_aninexus_runtime
from webapp_routes.source_v2 import build_source_v2_router
from webapp_routes.terms import build_terms_router
from webapp_services.collection import collection_cards_from_snapshot, collection_snapshot

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
profile_page_router = build_profile_page_router(default_banner_url=TOP_BANNER_URL)
collection_router = build_collection_router(banner_url=CARDS_TOP_BANNER_URL)
memory_router = build_memory_router(banner_url=CARDS_TOP_BANNER_URL)
terms_router = build_terms_router(
    required_channel_url=REQUIRED_CHANNEL_URL,
    top_banner_url=TOP_BANNER_URL,
    background_url=BACKGROUND_URL,
    empty_bg_data_uri=EMPTY_BG_DATA_URI,
)
source_v2_router = build_source_v2_router(banner_url=TOP_BANNER_URL)
aninexus_dado_router = build_aninexus_dado_router()
aninexus_games_router = build_aninexus_games_router()
aninexus_me_router = build_aninexus_me_router()
aninexus_pets_router = build_aninexus_pets_router()
aninexus_ranking_router = build_aninexus_ranking_router()
aninexus_shop_router = build_aninexus_shop_router()
aninexus_social_router = build_aninexus_social_router()
aninexus_progression_router = build_aninexus_progression_router()
aninexus_compat_router = build_aninexus_compat_router()


def _install_runtime_routes() -> None:
    install_aninexus_runtime(app)
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

    if "/api/v1_7b82/me" not in registered_paths:
        app.include_router(aninexus_me_router)
        registered_paths.add("/api/v1_7b82/me")

    aninexus_dado_paths = {
        "/api/v1_7b82/dado/state",
        "/api/v1_7b82/dado/roll",
        "/api/v1_7b82/dado/pick",
    }
    if not aninexus_dado_paths.issubset(registered_paths):
        app.include_router(aninexus_dado_router)
        registered_paths.update(aninexus_dado_paths)

    aninexus_games_paths = {
        "/api/v1_7b82/minigames/state",
        "/api/v1_7b82/minigames/start/{game_type}",
        "/api/v1_7b82/minigames/submit",
    }
    if not aninexus_games_paths.issubset(registered_paths):
        app.include_router(aninexus_games_router)
        registered_paths.update(aninexus_games_paths)

    if "/api/v1_7b82/leaderboard" not in registered_paths:
        app.include_router(aninexus_ranking_router)
        registered_paths.add("/api/v1_7b82/leaderboard")

    aninexus_shop_paths = {
        "/api/v1_7b82/source-shop",
        "/api/v1_7b82/source-shop/buy-dado",
        "/api/v1_7b82/source-shop/buy-xcard/{slot_code}",
    }
    if not aninexus_shop_paths.issubset(registered_paths):
        app.include_router(aninexus_shop_router)
        registered_paths.update(aninexus_shop_paths)

    aninexus_social_paths = {
        "/api/v1_7b82/social/referrals",
        "/api/v1_7b82/social/referrals/stats",
        "/api/v1_7b82/social/referrals/claim",
        "/api/v1_7b82/trade/user/{target_user_id}/collection",
        "/api/v1_7b82/trade/offers",
        "/api/v1_7b82/trade/offer",
        "/api/v1_7b82/trade/respond/{trade_id}",
        "/api/v1_7b82/economy",
    }
    if not aninexus_social_paths.issubset(registered_paths):
        app.include_router(aninexus_social_router)
        registered_paths.update(aninexus_social_paths)

    aninexus_pets_paths = {
        "/api/v1_7b82/shop/pets",
        "/api/v1_7b82/shop/buy/pet/{pet_ref}",
        "/api/v1_7b82/pets/set_active/{pet_ref}",
        "/api/v1_7b82/pets/feed",
        "/api/v1_7b82/pets/train",
        "/api/v1_7b82/eggs/incubate/{egg_id}",
        "/api/v1_7b82/eggs/hatch/{egg_id}",
        "/api/v1_7b82/eggs/sell/{egg_id}",
        "/api/v1_7b82/eggs/purify/{egg_id}",
        "/api/v1_7b82/eggs/fuse/{tier}",
    }
    if not aninexus_pets_paths.issubset(registered_paths):
        app.include_router(aninexus_pets_router)
        registered_paths.update(aninexus_pets_paths)

    aninexus_progression_paths = {
        "/api/v1_7b82/achievements/list",
        "/api/v1_7b82/quests",
        "/api/v1_7b82/quests/claim/{quest_id}",
        "/api/v1_7b82/pass_data",
        "/api/v1_7b82/claim_level/{level}",
        "/api/v1_7b82/buy_level",
        "/api/v1_7b82/claim_bank",
    }
    if not aninexus_progression_paths.issubset(registered_paths):
        app.include_router(aninexus_progression_router)
        registered_paths.update(aninexus_progression_paths)

    aninexus_compat_paths = {
        "/api/v1_7b82/secure_init",
        "/api/v1_7b82/harem",
        "/api/v1_7b82/rarities",
        "/api/v1_7b82/social/marriage",
        "/api/v1_7b82/battle/stats",
    }
    if not aninexus_compat_paths.issubset(registered_paths):
        app.include_router(aninexus_compat_router)
        registered_paths.update(aninexus_compat_paths)

    terms_paths = {"/terms", "/api/terms/accept", "/api/terms/decline"}
    if not terms_paths.issubset(registered_paths):
        app.include_router(terms_router)
        registered_paths.update(terms_paths)

    source_v2_paths = {"/source-v2", "/app-v2"}
    if not source_v2_paths.issubset(registered_paths):
        app.include_router(source_v2_router)
        registered_paths.update(source_v2_paths)

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

    profile_collection_paths = {"/api/menu/collection-characters", "/api/menu/favorite"}
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

    memory_paths = {"/memoria", "/memory", "/api/memory/best", "/api/memory/finish"}
    if not memory_paths.issubset(registered_paths):
        app.include_router(memory_router)


def _install_runtime_middleware() -> None:
    if any(middleware.cls is RequestObservabilityMiddleware for middleware in app.user_middleware):
        return
    app.add_middleware(RequestObservabilityMiddleware)


_install_runtime_routes()
_install_runtime_middleware()
