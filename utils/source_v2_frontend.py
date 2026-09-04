from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def source_v2_static_dir() -> Path:
    configured = str(os.getenv("SOURCE_V2_STATIC_DIR", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "webapp_v2_static").resolve()


def install_source_v2_frontend(app: FastAPI) -> bool:
    """Mount the built React app at /v2 when its build directory exists."""

    if any(getattr(route, "path", "") == "/v2" for route in app.routes):
        return True

    directory = source_v2_static_dir()
    index_path = directory / "index.html"
    if not index_path.is_file():
        return False

    # The imported frontend uses hash-based tabs, so StaticFiles(html=True) is
    # sufficient and keeps all Vite assets under the isolated /v2 namespace.
    app.mount(
        "/v2",
        StaticFiles(directory=str(directory), html=True, check_dir=True),
        name="source-v2-miniapp",
    )
    return True
