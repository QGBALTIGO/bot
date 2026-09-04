from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from database_seal_progression import (
    buy_pass_levels,
    claim_pass_level,
    claim_quest,
    get_daily_selection,
    get_eggs,
    get_pass_state,
    get_titles,
    get_unlocked_achievement_ids,
    get_wallet,
    is_quest_claimed,
    quest_progress,
    sync_achievements,
)
from seal_progression import (
    ACHIEVEMENTS,
    CURRENT_PASS_SEASON,
    LEVEL_BUY_SHARD_COST,
    MAX_PASS_LEVEL,
    PASS_BENEFITS,
    PASS_MILESTONES,
    PASS_MISSIONS,
    PASS_SEASON_NAME,
    PASS_STAR_PRICES,
    PASS_TIER_META,
    PASS_TRACKS,
    QUEST_POOL,
    WEEKLY_POOL,
    calculate_pass_upgrade_price,
    get_progress_values,
    normalize_pass_tier,
)
from webapp_routes.seal_compat import (
    API_PREFIX,
    _require_user,
    _unauthorized,
    _user_payload as _source_user_payload,
)


def _error(message: str, code: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
    )


def _auth(authorization: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        return _require_user(authorization), None
    except PermissionError as exc:
        return None, _unauthorized(str(exc))


def _quest_item(
    user_id: int,
    quest_id: str,
    definition: dict[str, Any],
    *,
    locked: bool = False,
) -> dict[str, Any]:
    progress = min(
        int(definition["target"]),
        max(0, int(quest_progress(user_id, quest_id))),
    )
    return {
        "id": quest_id,
        "name": str(definition["name"]),
        "description": str(definition["description"]),
        "icon": str(definition.get("icon") or "◉"),
        "reward_xp": int(definition["reward_xp"]),
        "reward_shards": int(definition["reward_shards"]),
        "progress": progress,
        "target": int(definition["target"]),
        "claimed": is_quest_claimed(user_id, quest_id),
        "locked": bool(locked),
    }


def build_seal_progression_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["seal-progression"])

    def me(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)

        sync_achievements(user_id)
        wallet = get_wallet(user_id)
        pass_state = get_pass_state(user_id)
        eggs = get_eggs(user_id)
        unlocked_ids = sorted(get_unlocked_achievement_ids(user_id))
        titles = get_titles(user_id)
        progress = get_progress_values(int(wallet.get("xp") or 0))
        pass_type = normalize_pass_tier(pass_state.get("pass_type"))

        payload = _source_user_payload(session_user)
        payload["balance"] = int(wallet.get("shards") or 0)
        payload["zenith"] = int(wallet.get("zenith") or 0)
        payload["achievements"] = unlocked_ids
        payload["titles"] = {
            "current": titles[-1] if titles else "OPERATOR",
            "all": titles or ["OPERATOR"],
        }
        payload["eggs"] = eggs

        stats = dict(payload.get("stats") or {})
        stats.update(
            {
                "level": int(progress["level"]),
                "xp": int(progress["xp"]),
                "xp_current": int(progress["xp_current"]),
                "xp_needed": int(progress["xp_needed"]),
                "points": int(wallet.get("shards") or 0),
                "zenith": int(wallet.get("zenith") or 0),
                "pass_type": pass_type,
                "incubation_slots": int(PASS_BENEFITS[pass_type]["incubation_slots"]),
                "active_incubations": sum(
                    1 for egg in eggs if str(egg.get("status") or "") == "incubating"
                ),
            }
        )
        payload["stats"] = stats
        return JSONResponse(payload)

    def achievements(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        sync_achievements(user_id)
        unlocked = get_unlocked_achievement_ids(user_id)
        return JSONResponse(
            [
                {
                    "id": achievement_id,
                    "name": str(definition["name"]),
                    "description": str(definition["description"]),
                    "icon": str(definition.get("icon") or "🏆"),
                    "reward_xp": int(definition["reward_xp"]),
                    "unlocked": achievement_id in unlocked,
                }
                for achievement_id, definition in ACHIEVEMENTS.items()
            ]
        )

    def quests(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        pass_type = normalize_pass_tier(get_pass_state(user_id).get("pass_type"))
        daily_ids = get_daily_selection(user_id)
        return JSONResponse(
            {
                "daily": [
                    _quest_item(user_id, quest_id, QUEST_POOL[quest_id])
                    for quest_id in daily_ids
                    if quest_id in QUEST_POOL
                ],
                "weekly": [
                    _quest_item(user_id, quest_id, definition)
                    for quest_id, definition in WEEKLY_POOL.items()
                ],
                "pass": [
                    _quest_item(
                        user_id,
                        quest_id,
                        definition,
                        locked=pass_type == "free",
                    )
                    for quest_id, definition in PASS_MISSIONS.items()
                ],
                "pass_type": pass_type,
            }
        )

    def claim_quest_endpoint(
        quest_id: str,
        authorization: str = Header(default=""),
    ):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = claim_quest(int(session_user.get("id") or 0), quest_id)
        if result.get("ok"):
            return JSONResponse(
                {
                    "success": True,
                    "reward_xp": int(result.get("reward_xp") or 0),
                    "reward_shards": int(result.get("reward_shards") or 0),
                }
            )
        error_code = str(result.get("error") or "quest_error")
        messages = {
            "quest_not_active": "Quest not active today.",
            "quest_not_found": "Quest not found.",
            "quest_incomplete": "Quest not completed.",
            "already_claimed": "Already claimed.",
            "pass_required": "This mission requires Premium or Elite Pass.",
        }
        return _error(messages.get(error_code, "Could not claim quest."), error_code)

    def pass_data(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        wallet = get_wallet(user_id)
        state = get_pass_state(user_id)
        progress = get_progress_values(int(wallet.get("xp") or 0))
        pass_type = normalize_pass_tier(state.get("pass_type"))
        pass_bank = dict(state.get("pass_bank") or {})
        return JSONResponse(
            {
                **progress,
                "season_id": CURRENT_PASS_SEASON,
                "season_name": PASS_SEASON_NAME,
                "pass_type": pass_type,
                "pass_bank": pass_bank,
                "pass_bank_total": int(pass_bank.get("shards") or 0)
                + sum(
                    int(value or 0)
                    for key, value in pass_bank.items()
                    if str(key).startswith("eggs_t")
                ),
                "claimed_levels": [int(x) for x in (state.get("claimed_levels") or [])],
                "tracks": PASS_TRACKS,
                "milestones": PASS_MILESTONES,
                "max_level": MAX_PASS_LEVEL,
                "prices": PASS_STAR_PRICES,
                "currency": "XTR",
                "upgrade_prices": {
                    tier: calculate_pass_upgrade_price(pass_type, tier)
                    for tier in ("premium", "elite")
                },
                "level_buy_cost": LEVEL_BUY_SHARD_COST,
                "benefits": PASS_BENEFITS,
                "tiers": PASS_TIER_META,
            }
        )

    def claim_level(level: int, authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = claim_pass_level(int(session_user.get("id") or 0), level)
        if result.get("ok"):
            return JSONResponse(
                {
                    "status": str(result.get("status") or "success"),
                    "shards": int(result.get("shards") or 0),
                    "eggs": int(result.get("eggs") or 0),
                }
            )
        code = str(result.get("error") or "pass_claim_error")
        messages = {
            "invalid_level": "Invalid level.",
            "level_not_reached": f"Level {level} not reached yet.",
        }
        return _error(messages.get(code, "Could not claim this level."), code)

    def buy_level(
        levels: int = Query(default=1, ge=1, le=50),
        authorization: str = Header(default=""),
    ):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        result = buy_pass_levels(int(session_user.get("id") or 0), levels)
        if not result.get("ok"):
            return _error(
                f"Insufficient Coins (Need {int(result.get('cost') or 0):,})",
                str(result.get("error") or "buy_level_failed"),
            )
        return JSONResponse(
            {
                "status": "success",
                "message": f"Bought {int(result['levels'])} levels for {int(result['cost']):,} Coins!",
            }
        )

    def claim_bank(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        state = get_pass_state(int(session_user.get("id") or 0))
        if normalize_pass_tier(state.get("pass_type")) == "free":
            return _error("Must upgrade pass to claim bank.", "pass_required")
        return _error("Bank is empty.", "bank_empty")

    def shop_hub(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        user_id = int(session_user.get("id") or 0)
        wallet = get_wallet(user_id)
        state = get_pass_state(user_id)
        now = datetime.now(timezone.utc)
        reset_at = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return JSONResponse(
            {
                "balance": int(wallet.get("shards") or 0),
                "zenith": int(wallet.get("zenith") or 0),
                "pass_type": normalize_pass_tier(state.get("pass_type")),
                "characters_rarity": "Various",
                "rotation_date": now.date().isoformat(),
                "reset_at": reset_at.isoformat(),
                "exchange_rate": 10_000,
            }
        )

    def exchange_data(authorization: str = Header(default="")):
        session_user, error = _auth(authorization)
        if error:
            return error
        assert session_user is not None
        wallet = get_wallet(int(session_user.get("id") or 0))
        return JSONResponse(
            {
                "balance": int(wallet.get("shards") or 0),
                "zenith": int(wallet.get("zenith") or 0),
                "rate": 10_000,
                "minimum_shards": 10_000,
                "minimum_zenith": 1,
            }
        )

    router.add_api_route("/me", me, methods=["GET"])
    router.add_api_route("/achievements/list", achievements, methods=["GET"])
    router.add_api_route("/quests", quests, methods=["GET"])
    router.add_api_route("/quests/claim/{quest_id}", claim_quest_endpoint, methods=["POST"])
    router.add_api_route("/pass_data", pass_data, methods=["GET"])
    router.add_api_route("/claim_level/{level}", claim_level, methods=["POST"])
    router.add_api_route("/buy_level", buy_level, methods=["POST"])
    router.add_api_route("/claim_bank", claim_bank, methods=["POST"])
    router.add_api_route("/shop/hub", shop_hub, methods=["GET"])
    router.add_api_route("/shop/exchange", exchange_data, methods=["GET"])
    return router
