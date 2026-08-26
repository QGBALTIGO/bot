from __future__ import annotations

from collection_webapp import register_collection_routes
from game_webapp import register_game_routes
from profile_webapp import register_profile_routes
from ranking_webapp import register_ranking_routes
from shop_webapp import register_shop_routes


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
}


def register_v2_routes(app) -> None:
    register_game_routes(app)
    register_collection_routes(app)
    register_profile_routes(app)
    register_ranking_routes(app)
    register_shop_routes(app)
