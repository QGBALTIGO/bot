from __future__ import annotations

import os

from fastapi.responses import JSONResponse

from utils.public_url import get_public_base_url


def register_health_routes(app) -> None:
    @app.get('/healthz')
    async def healthz():
        commit = str(os.getenv('RAILWAY_GIT_COMMIT_SHA', '') or '').strip()
        return JSONResponse({
            'ok': True,
            'service': 'source-baltigo',
            'generation': 'v2',
            'webapp_auth': 'signed-launch-session-v1',
            'commit': commit[:12] if commit else '',
            'public_base_url': get_public_base_url(),
            'routes': len(getattr(app, 'routes', []) or []),
        })
