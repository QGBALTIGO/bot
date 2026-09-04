from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


ROOT_DIR = Path(__file__).resolve().parents[1]
SEAL_RUNTIME_DIR = ROOT_DIR / "seal_runtime"
SEAL_ASSETS_DIR = SEAL_RUNTIME_DIR / "assets"


def install_seal_runtime(app: FastAPI) -> None:
    """Serve o build gerado a partir do frontend upstream sem editar seus arquivos."""

    index_file = SEAL_RUNTIME_DIR / "index.html"
    if not index_file.is_file() or not SEAL_ASSETS_DIR.is_dir():
        raise RuntimeError(
            "seal_runtime ausente. Gere o build do frontend exato antes do deploy."
        )

    existing_paths = {getattr(route, "path", "") for route in app.routes}

    if "/assets" not in existing_paths:
        app.mount(
            "/assets",
            StaticFiles(directory=str(SEAL_ASSETS_DIR)),
            name="seal-assets",
        )
        existing_paths.add("/assets")

    def seal_favicon():
        return FileResponse(SEAL_RUNTIME_DIR / "favicon.svg")

    def seal_icons():
        return FileResponse(SEAL_RUNTIME_DIR / "icons.svg")

    def seal_menu():
        return FileResponse(index_file, media_type="text/html")

    def seal_preview():
        return FileResponse(index_file, media_type="text/html")

    # Registra programaticamente para que exista apenas uma declaração estática
    # de /menu no código legado; em runtime este handler é instalado primeiro e
    # assume a rota antes do fallback antigo.
    if "/favicon.svg" not in existing_paths:
        app.add_api_route(
            "/favicon.svg",
            seal_favicon,
            methods=["GET"],
            include_in_schema=False,
        )
        existing_paths.add("/favicon.svg")

    if "/icons.svg" not in existing_paths:
        app.add_api_route(
            "/icons.svg",
            seal_icons,
            methods=["GET"],
            include_in_schema=False,
        )
        existing_paths.add("/icons.svg")

    if "/menu" not in existing_paths:
        app.add_api_route(
            "/menu",
            seal_menu,
            methods=["GET"],
            include_in_schema=False,
        )
        existing_paths.add("/menu")

    if "/seal" not in existing_paths:
        app.add_api_route(
            "/seal",
            seal_preview,
            methods=["GET"],
            include_in_schema=False,
        )
