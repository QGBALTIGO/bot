from __future__ import annotations

from fastapi.responses import JSONResponse

from utils.public_url import get_public_base_url


def register_health_routes(app) -> None:
    @app.get('/healthz')
    async def healthz():
        return JSONResponse({
            'ok': True,
            'service': 'source-baltigo',
            'generation': 'v2',
            'public_base_url': get_public_base_url(),
            'routes': len(getattr(app, 'routes', []) or []),
        })
