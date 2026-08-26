from __future__ import annotations

from collection_webapp import register_collection_routes
from contrib_webapp import register_contribution_routes
from game_webapp import register_game_routes
from hub_webapp import register_hub_routes
from memory_webapp import register_memory_routes
from messages_webapp import register_message_routes
from profile_webapp import register_profile_routes
from ranking_webapp import register_ranking_routes
from shop_webapp import register_shop_routes
from termo_webapp import register_termo_routes
from xcards_webapp import register_xcards_routes


PROTECTED_V2_PATHS = {
    "/api/v2/game/state",
    "/api/v2/game/daily/claim",
    "/api/v2/game/dice/roll",
    "/api/v2/game/dice/pick",
    "/api/v2/game/spin",
    "/api/v2/collection",
    "/api/v2/profile",
    "/api/v2/ranking",
    "/api/v2/shop",
    "/api/v2/shop/buy",
    "/api/v2/shop/sell",
    "/api/v2/xcards/state",
    "/api/v2/xcards/buy",
    "/api/v2/memory/stats",
    "/api/v2/memory/start",
    "/api/v2/memory/finish",
    "/api/v2/termo/state",
    "/api/v2/termo/start",
    "/api/v2/termo/train",
    "/api/v2/termo/guess",
    "/api/v2/termo/hint",
    "/api/v2/messages/state",
    "/api/v2/messages/settings",
    "/api/v2/messages/block",
    "/api/v2/messages/report",
    "/api/v2/contrib/state",
    "/api/v2/contrib/image",
    "/api/v2/contrib/work",
    "/api/v2/contrib/admin/pending",
    "/api/v2/contrib/admin/review",
    "/api/v2/ecosystem/state",
    "/api/v2/search",
    "/api/v2/library/save",
    "/api/v2/library/remove",
    "/api/v2/missions/claim",
    "/api/v2/titles/equip",
    "/api/v2/notifications/preferences",
    "/api/v2/notifications/read",
    "/api/v2/friends/request",
    "/api/v2/friends/respond",
}


def register_v2_routes(app) -> None:
    register_game_routes(app)
    register_collection_routes(app)
    register_profile_routes(app)
    register_ranking_routes(app)
    register_shop_routes(app)
    register_xcards_routes(app)
    register_memory_routes(app)
    register_termo_routes(app)
    register_message_routes(app)
    register_contribution_routes(app)
    register_hub_routes(app)
