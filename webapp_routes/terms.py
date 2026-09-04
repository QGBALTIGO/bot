from __future__ import annotations

import traceback

from fastapi import APIRouter, Body, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from utils.webapp_identity import resolve_webapp_user as _resolve_webapp_user
from webapp_services.terms import TERMS_HTML, TERMS_LONG, TERMS_VERSION, TEXTS, pick_lang


def build_terms_router(
    *,
    required_channel_url: str,
    top_banner_url: str,
    background_url: str,
    empty_bg_data_uri: str,
) -> APIRouter:
    router = APIRouter(tags=["terms"])

    @router.get("/terms", response_class=HTMLResponse)
    def terms_page(uid: int = Query(...), lang: str = Query("en")):
        language = pick_lang(lang)
        texts = TEXTS[language]
        body = TERMS_LONG[language]

        joinblock = f"""
        <div class="colBlock">
          <div class="colTitle">{texts["join_title"]}</div>
          <div class="colText">{texts["join_text"]}</div>
          <div class="rowBtns">
            <a class="smallBtn" href="{required_channel_url}" target="_blank" rel="noopener noreferrer">{texts["join_button"]}</a>
            <button type="button" class="smallBtn smallBtnPrimary" id="checkChannelBtn">{texts["verify_button"]}</button>
          </div>
        </div>
        """

        bg = background_url if background_url else empty_bg_data_uri
        html = (
            TERMS_HTML
            .replace("__UID__", str(uid))
            .replace("__LANG__", language)
            .replace("__LANGCODE__", language.upper())
            .replace("__TITLE__", texts["title"])
            .replace("__SUBTITLE__", texts["subtitle"])
            .replace("__INTRO__", texts["intro"])
            .replace("__CHECK1__", texts["check1"])
            .replace("__CHECK2__", texts["check2"])
            .replace("__ACCEPT__", texts["accept"])
            .replace("__DECLINE__", texts["decline"])
            .replace("__DONE__", texts["done"])
            .replace("__NO__", texts["no"])
            .replace("__ERROR__", texts["error"])
            .replace("__NEEDCHECKS__", texts["need_checks"])
            .replace("__JOINNEEDED__", texts["join_needed"])
            .replace("__SAVING__", texts["saving"])
            .replace("__PROCESSING__", texts["processing"])
            .replace("__VERIFYOK__", texts["verify_ok"])
            .replace("__VERIFYFAIL__", texts["verify_fail"])
            .replace("__VERIFYCONF__", texts["verify_confirmed"])
            .replace("__TVERSION__", TERMS_VERSION.upper())
            .replace("__BODY__", body)
            .replace("__JOINBLOCK__", joinblock)
            .replace("__TOPBANNER__", top_banner_url)
            .replace("__BGURL__", bg)
        )
        return HTMLResponse(html)

    @router.post("/api/terms/accept")
    def api_accept(
        payload: dict = Body(...),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        from database import accept_terms, create_or_get_user, set_language

        try:
            ctx = _resolve_webapp_user(
                x_telegram_init_data=x_telegram_init_data,
                x_webapp_uid=x_webapp_uid,
                body_uid=payload.get("uid"),
            )
            user_id = int(ctx["user_id"])
            language = pick_lang(payload.get("lang"))

            create_or_get_user(user_id)
            set_language(user_id, language)
            accept_terms(user_id, TERMS_VERSION)
            return {"ok": True, "message": TEXTS[language]["done"]}
        except HTTPException:
            raise
        except Exception as exc:
            print(f"[terms] accept failed type={type(exc).__name__}", flush=True)
            traceback.print_exc()
            return JSONResponse(
                {"ok": False, "message": TEXTS[pick_lang(payload.get("lang"))]["error"]},
                status_code=500,
            )

    @router.post("/api/terms/decline")
    def api_decline(
        payload: dict = Body(...),
        x_telegram_init_data: str = Header(default=""),
        x_webapp_uid: str = Header(default=""),
    ):
        from database import create_or_get_user, set_language

        try:
            ctx = _resolve_webapp_user(
                x_telegram_init_data=x_telegram_init_data,
                x_webapp_uid=x_webapp_uid,
                body_uid=payload.get("uid"),
            )
            user_id = int(ctx["user_id"])
            language = pick_lang(payload.get("lang"))

            create_or_get_user(user_id)
            set_language(user_id, language)
            return {"ok": True, "message": TEXTS[language]["no"]}
        except HTTPException:
            raise
        except Exception as exc:
            print(f"[terms] decline failed type={type(exc).__name__}", flush=True)
            traceback.print_exc()
            return JSONResponse(
                {"ok": False, "message": TEXTS[pick_lang(payload.get("lang"))]["error"]},
                status_code=500,
            )

    return router
