from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_image_proxy_route_lives_outside_webapp_monolith() -> None:
    legacy = (ROOT / "webapp.py").read_text(encoding="utf-8")
    module = (ROOT / "webapp_routes" / "image_proxy.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "webapp_entrypoint.py").read_text(encoding="utf-8")

    assert '@app.get("/api/image-proxy")' not in legacy
    assert '@router.get("/api/image-proxy")' in module
    assert "from webapp_routes.image_proxy import router as image_proxy_router" in entrypoint
    assert "app.include_router(image_proxy_router)" in entrypoint


def test_image_proxy_contract_is_preserved() -> None:
    module = (ROOT / "webapp_routes" / "image_proxy.py").read_text(encoding="utf-8")

    assert 'Query(..., min_length=8, max_length=2000)' in module
    assert 'Query("", max_length=20)' in module
    assert '"X-Image-Crop": "2:3" if applied_crop else "original"' in module
    assert '"Cache-Control": "public, max-age=604800, stale-while-revalidate=86400"' in module
