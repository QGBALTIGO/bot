from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from premium_webapp_ui import build_media_catalog_page as build_media_catalog_page_html
from webapp_services import catalog as catalog_service

router = APIRouter(tags=["catalog"])


@router.get("/api/letters")
def api_letters():
    return JSONResponse(catalog_service.catalog_letters_payload())


@router.get("/api/catalogo")
def api_catalogo(
    q: str = Query(default="", max_length=80),
    letter: str = Query(default="ALL", max_length=3),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = catalog_service.filter_catalog(
        q=q,
        letter=letter,
        limit=limit,
        offset=offset,
    )
    return JSONResponse({"total": total, "items": items})


@router.get("/catalogo", response_class=HTMLResponse)
def catalogo_page():
    return HTMLResponse(
        build_media_catalog_page_html(
            page_title=f"{catalog_service.CATALOG_TITLE} - Source Baltigo",
            hero_tag="Anime catalog",
            hero_title=catalog_service.CATALOG_TITLE,
            hero_copy="Biblioteca com visual mais premium, hierarquia melhor e navegacao mais gostosa para mobile.",
            banner_url=catalog_service.CATALOG_BANNER_URL,
            api_letters="/api/letters",
            api_catalog="/api/catalogo",
            search_placeholder="Buscar anime...",
            footer_label="Source Baltigo . Catalogo",
            default_badge="Anime",
        )
    )


@router.get("/api/mangas/letters")
def api_mangas_letters():
    return JSONResponse(catalog_service.manga_letters_payload())


@router.get("/api/mangas/catalogo")
def api_mangas_catalogo(
    q: str = Query(default="", max_length=80),
    letter: str = Query(default="ALL", max_length=3),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = catalog_service.filter_manga_catalog(
        q=q,
        letter=letter,
        limit=limit,
        offset=offset,
    )
    return JSONResponse({"total": total, "items": items})


@router.get("/mangas", response_class=HTMLResponse)
def mangas_page():
    return HTMLResponse(
        build_media_catalog_page_html(
            page_title=f"{catalog_service.MANGA_CATALOG_TITLE} - Source Baltigo",
            hero_tag="Manga catalog",
            hero_title=catalog_service.MANGA_CATALOG_TITLE,
            hero_copy="Uma vitrine mais cinematografica para explorar mangas com foco em legibilidade, contraste e ritmo visual.",
            banner_url=catalog_service.MANGA_CATALOG_BANNER_URL,
            api_letters="/api/mangas/letters",
            api_catalog="/api/mangas/catalogo",
            search_placeholder="Buscar manga...",
            footer_label="Source Baltigo . Mangas",
            default_badge="Manga",
        )
    )
