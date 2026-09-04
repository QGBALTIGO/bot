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
    """Mount the untouched Seal frontend build without modifying its asset paths."""

    mount_at_root = str(os.getenv("SOURCE_V2_FRONTEND_ROOT", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    mount_path = "/" if mount_at_root else "/v2"
    mount_name = "source-v2-miniapp-root" if mount_at_root else "source-v2-miniapp"

    if any(getattr(route, "name", "") == mount_name for route in app.routes):
        return True

    directory = source_v2_static_dir()
    index_path = directory / "index.html"
    if not index_path.is_file():
        return False

    # The original Seal Vite build uses root-relative assets. Staging therefore
    # mounts it at / instead of editing vite.config/index.html/frontend code.
    app.mount(
        mount_path,
        StaticFiles(directory=str(directory), html=True, check_dir=True),
        name=mount_name,
    )
    return True
