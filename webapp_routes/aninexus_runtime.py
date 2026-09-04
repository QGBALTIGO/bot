from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


ROOT_DIR = Path(__file__).resolve().parents[1]
ANINEXUS_RUNTIME_DIR = ROOT_DIR / "aninexus_runtime"
ANINEXUS_ASSETS_DIR = ANINEXUS_RUNTIME_DIR / "assets"


def install_aninexus_runtime(app: FastAPI) -> None:
    """Serve o build compilado da MiniApp AniNexus."""

    index_file = ANINEXUS_RUNTIME_DIR / "index.html"
    if not index_file.is_file() or not ANINEXUS_ASSETS_DIR.is_dir():
        raise RuntimeError(
            "aninexus_runtime ausente. Gere o build da MiniApp AniNexus antes do deploy."
        )

    existing_paths = {getattr(route, "path", "") for route in app.routes}

    if "/assets" not in existing_paths:
        app.mount(
            "/assets",
            StaticFiles(directory=str(ANINEXUS_ASSETS_DIR)),
            name="aninexus-assets",
        )
        existing_paths.add("/assets")

    def aninexus_favicon():
        return FileResponse(ANINEXUS_RUNTIME_DIR / "favicon.svg")

    def aninexus_icons():
        return FileResponse(ANINEXUS_RUNTIME_DIR / "icons.svg")

    def aninexus_menu():
        return FileResponse(index_file, media_type="text/html")

    def aninexus_preview():
        return FileResponse(index_file, media_type="text/html")

    # Registra programaticamente para que exista apenas uma declaração estática
    # de /menu no código legado; este runtime é instalado primeiro e assume a rota.
    if "/favicon.svg" not in existing_paths:
        app.add_api_route(
            "/favicon.svg",
            aninexus_favicon,
            methods=["GET"],
            include_in_schema=False,
        )
        existing_paths.add("/favicon.svg")

    if "/icons.svg" not in existing_paths:
        app.add_api_route(
            "/icons.svg",
            aninexus_icons,
            methods=["GET"],
            include_in_schema=False,
        )
        existing_paths.add("/icons.svg")

    if "/menu" not in existing_paths:
        app.add_api_route(
            "/menu",
            aninexus_menu,
            methods=["GET"],
            include_in_schema=False,
        )
        existing_paths.add("/menu")

    if "/aninexus" not in existing_paths:
        app.add_api_route(
            "/aninexus",
            aninexus_preview,
            methods=["GET"],
            include_in_schema=False,
        )
