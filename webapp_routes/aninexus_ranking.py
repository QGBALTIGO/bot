from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from database import (
    get_all_coin_ranking_rows,
    get_all_collection_ranking_rows,
    get_all_memory_ranking_rows,
    get_termo_global_ranking,
    get_top_level_users,
)
from webapp_routes.seal_compat import API_PREFIX, _require_user, _unauthorized


def _auth(authorization: str) -> JSONResponse | None:
    try:
        _require_user(authorization)
        return None
    except PermissionError as exc:
        return _unauthorized(str(exc))


def _identity(row: dict[str, Any], rank: int, value: int | float) -> dict[str, Any]:
    user_id = int(row.get("user_id") or 0)
    full_name = str(row.get("nickname") or row.get("full_name") or "").strip()
    username = str(row.get("username") or "").strip().lstrip("@")
    return {
        "id": user_id,
        "rank": rank,
        "first_name": full_name or (f"@{username}" if username else f"Usuário {user_id}"),
        "full_name": full_name or None,
        "username": username or None,
        "avatar": None,
        "value": value,
    }


def _collection(limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in (get_all_collection_ranking_rows() or [])][:limit]
    return [_identity(row, i, int(row.get("total_cards") or 0)) for i, row in enumerate(rows, 1)]


def _coins(limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in (get_all_coin_ranking_rows() or [])][:limit]
    return [_identity(row, i, int(row.get("coins") or 0)) for i, row in enumerate(rows, 1)]


def _level(limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in (get_top_level_users(limit) or [])]
    return [_identity(row, i, int(row.get("level") or 1)) for i, row in enumerate(rows, 1)]


def _termo(limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in (get_termo_global_ranking(limit) or [])]
    return [_identity(row, i, int(row.get("wins") or 0)) for i, row in enumerate(rows, 1)]


def _memory(limit: int) -> list[dict[str, Any]]:
    rows = [dict(row) for row in (get_all_memory_ranking_rows() or [])][:limit]
    return [_identity(row, i, int(row.get("levels_completed") or 0)) for i, row in enumerate(rows, 1)]


def build_aninexus_ranking_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["aninexus-ranking"])
    loaders: dict[str, Callable[[int], list[dict[str, Any]]]] = {
        "collection": _collection,
        "harem": _collection,
        "coins": _coins,
        "shards": _coins,
        "level": _level,
        "termo": _termo,
        "guesses": _termo,
        "memory": _memory,
    }

    def leaderboard(
        metric: str = Query(default="collection", max_length=20),
        authorization: str = Header(default=""),
    ):
        error = _auth(authorization)
        if error:
            return error
        metric_key = str(metric or "collection").strip().lower()
        loader = loaders.get(metric_key, _collection)
        return JSONResponse(loader(100))

    router.add_api_route("/leaderboard", leaderboard, methods=["GET"])
    return router
