"""Collecting APIs installed on Source's existing FastAPI app and session prefix."""

from __future__ import annotations
import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from source_features import collection, activity, events, market, schemas, discovery
from source_features.common import FeatureError
from source_features.help import TOPICS
from utils.aninexus_admin import is_admin
from utils.runtime_guard import rate_limiter
from webapp_routes.aninexus_compat import API_PREFIX, _require_user


async def actor(request: Request, authorization: str = Header(default="")) -> int:
    try:
        uid = int(_require_user(authorization).get("id") or 0)
        if uid <= 0:
            raise PermissionError()
    except (PermissionError, ValueError) as exc:
        raise HTTPException(401, "Sessão expirada. Reabra a MiniApp.") from exc
    limit = 30 if request.method != "GET" else 120
    if not await rate_limiter.allow(f"collecting:{uid}:{request.method}", limit, 60):
        raise HTTPException(429, "Muitas ações. Aguarde um momento e tente novamente.")
    return uid


def administrator(uid: int = Depends(actor)) -> int:
    if not is_admin(uid):
        raise HTTPException(403, "Somente a administração pode gerenciar eventos.")
    return uid


def body(model):
    # Keep datetimes typed for the database; UUIDs become strings for stable hashing.
    return {
        key: str(value) if isinstance(value, UUID) else value
        for key, value in model.model_dump(exclude_none=True).items()
    }


def install(app):
    @app.exception_handler(FeatureError)
    async def feature_error(_request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
        )

    @app.exception_handler(pg_errors.RaiseException)
    async def collection_guard_error(_request, exc):
        reason = str(exc).splitlines()[0]
        known = {
            "source_card_protected": "Esse personagem está protegido. Desbloqueie ou altere seu favorito primeiro.",
            "source_card_reserved": "Esse personagem está reservado. Encerre o anúncio primeiro.",
        }
        if reason not in known:
            return JSONResponse(
                {
                    "error": {
                        "code": "operation_failed",
                        "message": "Não foi possível concluir a operação.",
                    }
                },
                status_code=500,
            )
        return JSONResponse(
            {"error": {"code": reason, "message": known[reason]}}, status_code=409
        )

    router = APIRouter(prefix=API_PREFIX + "/collecting", tags=["source-collecting"])

    @router.get("/settings")
    def get_settings(uid: int = Depends(actor)):
        return {**collection.settings(uid), "can_manage_events": is_admin(uid)}

    @router.patch("/settings")
    def set_settings(payload: schemas.Preferences, uid: int = Depends(actor)):
        return collection.save_settings(uid, body(payload))

    @router.get("/characters")
    def characters(
        q: str = Query(default="", max_length=80),
        view: str = Query(
            default="owned", pattern="^(owned|wishes|protected|duplicates|catalog)$"
        ),
        offset: int = Query(default=0, ge=0, le=100000),
        limit: int = Query(default=24, ge=1, le=40),
        uid: int = Depends(actor),
    ):
        return collection.cards(uid, q, view, offset, limit)

    @router.put("/characters/{character_id}/protection")
    def protection(
        character_id: int, payload: schemas.Toggle, uid: int = Depends(actor)
    ):
        return collection.set_protection(uid, character_id, payload.enabled)

    @router.post("/wishes")
    def wish(payload: schemas.Wish, uid: int = Depends(actor)):
        return collection.wishes(uid, payload.ids, payload.enabled)

    @router.post("/wishes/work/{anime_id}")
    def wish_work(anime_id: int, uid: int = Depends(actor)):
        return collection.wish_work(uid, anime_id)

    @router.get("/matches")
    def matches(
        offset: int = Query(default=0, ge=0, le=10000), uid: int = Depends(actor)
    ):
        return collection.matches(uid, offset)

    @router.get("/workshop")
    def workshop(uid: int = Depends(actor)):
        return collection.workshop_state(uid)

    @router.post("/workshop/preview")
    def preview(payload: schemas.Selection, uid: int = Depends(actor)):
        return collection.workshop_preview(uid, [i.model_dump() for i in payload.items])

    @router.post("/workshop/recycle")
    def recycle(payload: schemas.Recycle, uid: int = Depends(actor)):
        return collection.workshop_recycle(
            uid, [i.model_dump() for i in payload.items], str(payload.request_id)
        )

    @router.post("/workshop/craft")
    def craft(payload: schemas.Craft, uid: int = Depends(actor)):
        return collection.craft(uid, payload.recipe, str(payload.request_id))

    @router.get("/cosmetics/profile")
    def profile_cosmetic(uid: int = Depends(actor)):
        from database_core import run

        return run(
            "SELECT c.cosmetic_id,c.label,c.kind FROM source_collecting_settings s JOIN source_cosmetics c ON c.user_id=s.user_id AND c.cosmetic_id=s.equipped_cosmetic WHERE s.user_id=%s",
            (uid,),
            fetch="one",
        )

    @router.put("/cosmetics/equipped")
    def equip(payload: schemas.Equip, uid: int = Depends(actor)):
        return collection.equip(uid, payload.cosmetic_id)

    @router.get("/now")
    def now(uid: int = Depends(actor)):
        return activity.now(uid)

    @router.get("/calendar")
    def calendar(uid: int = Depends(actor)):
        return activity.calendar(uid)

    @router.post("/daily/claim")
    def daily(uid: int = Depends(actor)):
        return activity.claim(uid)

    @router.post("/daily/milestone")
    def milestone(uid: int = Depends(actor)):
        return activity.claim_milestone(uid)

    @router.get("/market")
    def market_list(
        mine: bool = False,
        offset: int = Query(default=0, ge=0, le=10000),
        uid: int = Depends(actor),
    ):
        return market.listings(uid, mine, offset)

    @router.post("/market")
    def market_create(payload: schemas.Listing, uid: int = Depends(actor)):
        return market.create(uid, body(payload))

    @router.post("/market/{listing_id}/action")
    def market_act(
        listing_id: UUID, payload: schemas.MarketAction, uid: int = Depends(actor)
    ):
        return market.act(
            uid,
            str(listing_id),
            payload.action,
            str(payload.request_id),
            payload.version,
            payload.amount,
        )

    @router.post("/market/{listing_id}/settle")
    def market_settle(listing_id: UUID, uid: int = Depends(actor)):
        return market.settle(str(listing_id), uid)

    @router.get("/events")
    def event_list(uid: int = Depends(actor)):
        return events.listing(uid, is_admin(uid))

    @router.post("/events")
    def event_create(payload: schemas.EventSpec, uid: int = Depends(administrator)):
        return events.create(uid, body(payload))

    @router.post("/events/{event_id}/publish")
    def event_publish(event_id: UUID, uid: int = Depends(administrator)):
        return events.publish(uid, str(event_id))

    @router.post("/events/{event_id}/contribute")
    def event_contribute(
        event_id: UUID, payload: schemas.Contribution, uid: int = Depends(actor)
    ):
        return events.contribute(
            uid, str(event_id), payload.character_id, str(payload.request_id)
        )

    @router.post("/events/{event_id}/claim")
    def event_claim(event_id: UUID, uid: int = Depends(actor)):
        return events.claim(uid, str(event_id))

    @router.get("/help")
    def help_topics(uid: int = Depends(actor)):
        return {
            "items": TOPICS,
            "inline_enabled_note": "A vitrine inline precisa estar habilitada no BotFather pelo administrador.",
        }

    @router.post("/identify")
    async def identify(request: Request, uid: int = Depends(actor)):
        if request.headers.get("X-Scene-Consent") != "yes":
            raise HTTPException(400, "Confirme o envio desta imagem ao trace.moe.")
        if not await rate_limiter.allow(f"scene:{uid}", 2, 60):
            raise HTTPException(
                429, "Aguarde um minuto antes de identificar outra cena."
            )
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > discovery.MAX_IMAGE:
                raise HTTPException(413, "Envie uma imagem de até 2 MB.")
        clean = await asyncio.to_thread(discovery.prepare_image, bytes(raw))
        from webapp import _get_http_client
        import httpx

        try:
            response = await _get_http_client().post(
                "https://api.trace.moe/search?anilistInfo",
                content=clean,
                headers={"Content-Type": "image/jpeg"},
                timeout=15.0,
                follow_redirects=False,
            )
            if response.status_code == 429:
                raise HTTPException(
                    429,
                    "O serviço de identificação atingiu seu limite. Tente mais tarde.",
                )
            response.raise_for_status()
            return discovery.normalize_results(response.json())
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(
                502,
                "A identificação está indisponível agora. Sua coleção não foi alterada.",
            ) from exc

    @router.get("/dice-info")
    def dice_info(anime_id: int = Query(default=0, ge=0), uid: int = Depends(actor)):
        from cards_service import build_cards_final_data
        from database_core import run

        data = build_cards_final_data()
        choices = data["characters_by_anime"].get(anime_id) or []
        history = run(
            "SELECT roll_id,dice_value,selected_anime_id,rewarded_character_id,status,created_at FROM dice_rolls WHERE user_id=%s ORDER BY roll_id DESC LIMIT 20",
            (uid,),
            fetch="all",
        )
        return {
            "rules": [
                "O dado sorteia a quantidade de obras, de uma até seis (ou até o total disponível).",
                "As obras são sorteadas sem repetição entre as elegíveis. Você escolhe uma delas.",
                "Cada personagem elegível da obra escolhida tem a mesma chance. O resultado é definido no servidor.",
                "A classificação exibida é calculada a partir do personagem e do dado; não é uma promessa de chance global fixa.",
            ],
            "guarantee_enabled": False,
            "guarantee_note": "Nenhuma garantia progressiva está ativa. Esta atualização não altera as probabilidades existentes.",
            "eligible_characters": len(choices),
            "character_probability": (1 / len(choices) if choices else None),
            "history": [
                {
                    **r,
                    "character_name": collection.character(
                        int(r["rewarded_character_id"])
                    )["name"]
                    if r["rewarded_character_id"]
                    else None,
                }
                for r in history
            ],
        }

    app.include_router(router)
